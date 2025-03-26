package com.jxev.ai.client;

import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.jxev.ai.server.MCPAccessibilityService;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.Socket;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * MCP Socket Client
 * Handles communication with the MCP Server via TCP socket connection.
 * Uses MCPAccessibilityService to execute UI automation actions.
 */
public class MCPSocketClient {
    private static final String TAG = "MCPSocketClient";

    // Socket connection parameters
    private String serverHost;
    private int serverPort;
    private Socket socket;
    private BufferedWriter writer;
    private BufferedReader reader;
    private boolean isConnected = false;
    private boolean isRunning = false;

    // Device info
    private final String deviceId;
    private final Context context;

    // Threading
    private final ExecutorService executorService = Executors.newCachedThreadPool();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    // Pending requests and callbacks
    private final Map<String, RequestCallback> pendingRequests = new ConcurrentHashMap<>();

    // Map to track action results from accessibility service
    private final Map<String, ActionResultCallback> pendingActions = new ConcurrentHashMap<>();

    // Connection callback
    private ConnectionCallback connectionCallback;

    // Heartbeat interval (in milliseconds)
    private static final long HEARTBEAT_INTERVAL = 30000; // 30 seconds

    // Store current package and activity
    private String currentPackage;
    private String currentActivity;

    // Store last UI state
    private JSONObject lastUIState;

    /**
     * Interface for request callbacks
     */
    public interface RequestCallback {
        void onResponse(JSONObject response);
        void onError(String error);
    }

    /**
     * Interface for action result callbacks
     */
    public interface ActionResultCallback {
        void onResult(Map<String, Object> result, String error);
    }

    /**
     * Interface for connection status callbacks
     */
    public interface ConnectionCallback {
        void onConnected();
        void onDisconnected(String reason);
        void onConnectionFailed(String error);
    }

    /**
     * Constructor
     * @param context Android context
     * @param serverHost Server hostname or IP
     * @param serverPort Server port
     */
    public MCPSocketClient(Context context, String serverHost, int serverPort) {
        this.context = context;
        this.serverHost = serverHost;
        this.serverPort = serverPort;

        // Generate a unique device ID or use Android ID
        this.deviceId = getDeviceId();
    }

    /**
     * Set connection callback
     * @param callback The callback to be invoked on connection events
     */
    public void setConnectionCallback(ConnectionCallback callback) {
        this.connectionCallback = callback;
    }

    /**
     * Connect to the MCP server
     */
    public void connect() {
        if (isConnected) {
            Log.w(TAG, "Already connected to server");
            return;
        }

        isRunning = true;

        executorService.execute(() -> {
            try {
                // Create socket connection
                socket = new Socket(serverHost, serverPort);
                writer = new BufferedWriter(new OutputStreamWriter(socket.getOutputStream()));
                reader = new BufferedReader(new InputStreamReader(socket.getInputStream()));

                // Perform handshake
                performHandshake();

                // Start message listening loop
                listenForMessages();

                // Start heartbeat
                startHeartbeat();

                isConnected = true;

                // Notify connection success
                if (connectionCallback != null) {
                    mainHandler.post(() -> connectionCallback.onConnected());
                }

            } catch (IOException e) {
                Log.e(TAG, "Connection failed: " + e.getMessage());

                if (connectionCallback != null) {
                    final String error = e.getMessage();
                    mainHandler.post(() -> connectionCallback.onConnectionFailed(error));
                }

                closeConnection("Connection error: " + e.getMessage());
            }
        });
    }

    /**
     * Disconnect from the MCP server
     */
    public void disconnect() {
        isRunning = false;
        closeConnection("User initiated disconnect");
    }

    /**
     * Close the socket connection and cleanup
     */
    private void closeConnection(String reason) {
        isRunning = false;

        try {
            if (socket != null && !socket.isClosed()) {
                socket.close();
            }

            if (writer != null) {
                writer.close();
            }

            if (reader != null) {
                reader.close();
            }
        } catch (IOException e) {
            Log.e(TAG, "Error closing connection: " + e.getMessage());
        }

        socket = null;
        writer = null;
        reader = null;
        isConnected = false;

        // Clear pending requests with error
        for (Map.Entry<String, RequestCallback> entry : pendingRequests.entrySet()) {
            entry.getValue().onError("Connection closed: " + reason);
        }
        pendingRequests.clear();

        // Notify disconnection
        if (connectionCallback != null) {
            mainHandler.post(() -> connectionCallback.onDisconnected(reason));
        }
    }

    /**
     * Cleanup resources
     */
    public void cleanup() {
        // Disconnect socket
        disconnect();
    }

    /**
     * Perform handshake with the server
     * @throws IOException if there's an error in the handshake
     */
    private void performHandshake() throws IOException {
        JSONObject handshakeMessage = new JSONObject();
        try {
            // Create handshake message in the format expected by the server
            handshakeMessage.put("type", "handshake");
            handshakeMessage.put("deviceId", deviceId);
            handshakeMessage.put("timestamp", System.currentTimeMillis() / 1000.0);

            // Add device info
            JSONObject deviceInfo = new JSONObject();
            deviceInfo.put("model", Build.MODEL);
            deviceInfo.put("manufacturer", Build.MANUFACTURER);
            deviceInfo.put("osVersion", Build.VERSION.RELEASE);
            deviceInfo.put("sdkVersion", Build.VERSION.SDK_INT);

            handshakeMessage.put("deviceInfo", deviceInfo);

            // Add capabilities
            JSONArray capabilities = new JSONArray();
            for (String capability : getDeviceCapabilities()) {
                capabilities.put(capability);
            }
            handshakeMessage.put("capabilities", capabilities);

            // Log the handshake message for debugging
            String messageStr = handshakeMessage.toString();
            Log.d(TAG, "Sending handshake message: " + messageStr);

            // Write directly to the socket
            writer.write(messageStr + "\n");
            writer.flush();

            // Wait for handshake response
            String response = reader.readLine();
            if (response == null) {
                throw new IOException("No handshake response received");
            }

            Log.d(TAG, "Received handshake response: " + response);

            JSONObject responseObj = new JSONObject(response);
            String type = responseObj.optString("type");
            String status = responseObj.optString("status");

            if (!"handshake_response".equals(type) || !"ok".equals(status)) {
                throw new IOException("Handshake failed: " + response);
            }

            Log.i(TAG, "Handshake successful");

        } catch (JSONException e) {
            Log.e(TAG, "JSON error in handshake: " + e.getMessage());
            throw new IOException("Error creating handshake message: " + e.getMessage());
        }
    }

    /**
     * Get device capabilities
     * @return Array of device capabilities
     */
    private String[] getDeviceCapabilities() {
        // Return a list of supported actions
        return new String[] {
                "click",
                "long_click",
                "swipe",
                "type_text",
                "scroll",
                "launch_app",
                "press_back",
                "press_home",
                "press_recents",
                "find_element",
                "get_text",
                "get_ui_state",
                "get_installed_apps"
        };
    }

    /**
     * Start the heartbeat mechanism
     */
    private void startHeartbeat() {
        executorService.execute(() -> {
            while (isRunning && isConnected) {
                try {
                    // Sleep for the heartbeat interval
                    Thread.sleep(HEARTBEAT_INTERVAL);

                    // Send heartbeat
                    if (isConnected) {
                        JSONObject heartbeat = new JSONObject();
                        heartbeat.put("type", "heartbeat");
                        heartbeat.put("deviceId", deviceId);
                        heartbeat.put("timestamp", System.currentTimeMillis() / 1000.0);

                        sendMessage(heartbeat);
                    }
                } catch (InterruptedException e) {
                    Log.w(TAG, "Heartbeat interrupted: " + e.getMessage());
                    Thread.currentThread().interrupt();
                    break;
                } catch (JSONException e) {
                    Log.e(TAG, "Error creating heartbeat message: " + e.getMessage());
                } catch (IOException e) {
                    Log.e(TAG, "Error sending heartbeat: " + e.getMessage());
                    closeConnection("Heartbeat failed: " + e.getMessage());
                    break;
                }
            }
        });
    }

    /**
     * Listen for incoming messages from the server
     */
    private void listenForMessages() {
        executorService.execute(() -> {
            try {
                String message;
                while (isRunning && (message = reader.readLine()) != null) {
                    final String receivedMessage = message;

                    try {
                        JSONObject jsonMessage = new JSONObject(receivedMessage);
                        String messageType = jsonMessage.optString("type");

                        switch (messageType) {
                            case "request":
                                handleRequest(jsonMessage);
                                break;
                            case "welcome":
                                Log.i(TAG, "Received welcome message: " + jsonMessage.optString("message"));
                                break;
                            case "heartbeat_response":
                                // Just log or ignore
                                break;
                            default:
                                Log.w(TAG, "Received unknown message type: " + messageType);
                                break;
                        }
                    } catch (JSONException e) {
                        Log.e(TAG, "Error parsing message: " + e.getMessage());
                    }
                }
            } catch (IOException e) {
                if (isRunning) {
                    Log.e(TAG, "Error reading from socket: " + e.getMessage());
                    closeConnection("Connection error: " + e.getMessage());
                }
            }
        });
    }

    /**
     * Handle incoming request from server
     * @param requestMessage The request message
     */
    private void handleRequest(JSONObject requestMessage) {
        try {
            String requestId = requestMessage.getString("requestId");
            String actionType = requestMessage.getString("actionType");
            JSONObject parameters = requestMessage.optJSONObject("parameters");
            if (parameters == null) {
                parameters = new JSONObject();
            }

            Log.i(TAG, "Received request: " + actionType + " with ID " + requestId);

            // Execute the action using MCPAccessibilityService
            executeAction(actionType, parameters, (result, error) -> {
                try {
                    // Create response message
                    JSONObject responseMessage = new JSONObject();
                    responseMessage.put("type", "response");
                    responseMessage.put("requestId", requestId);

                    // Create data object
                    JSONObject data = new JSONObject();

                    if (error != null) {
                        data.put("status", "error");
                        data.put("error", error);
                    } else {
                        data.put("status", "success");

                        // Add result if available
                        if (result != null) {
                            for (Map.Entry<String, Object> entry : result.entrySet()) {
                                data.put(entry.getKey(), entry.getValue());
                            }
                        }

                        // Add device state for certain actions
                        if (shouldIncludeDeviceState(actionType)) {
                            JSONObject deviceState = getDeviceState();
                            data.put("deviceState", deviceState);
                        }
                    }

                    responseMessage.put("data", data);
                    responseMessage.put("timestamp", System.currentTimeMillis() / 1000.0);

                    // Send response back to server
                    executorService.execute(() -> {
                        try {
                            sendMessage(responseMessage);
                        } catch (IOException e) {
                            Log.e(TAG, "Error sending response: " + e.getMessage());
                        }
                    });

                } catch (JSONException e) {
                    Log.e(TAG, "Error sending response: " + e.getMessage());
                }
            });

        } catch (JSONException e) {
            Log.e(TAG, "Error parsing request: " + e.getMessage());
        }
    }

    /**
     * Execute an action using MCPAccessibilityService
     */
    private void executeAction(String actionType, JSONObject parameters, ActionResultCallback callback) {
        // Map server action type to accessibility service action type if needed
        String accessibilityActionType = mapActionType(actionType);

        // Register callback
        String actionId = accessibilityActionType + "_" + System.currentTimeMillis();
        pendingActions.put(actionId, callback);

        // Set timeout for action
        mainHandler.postDelayed(() -> {
            ActionResultCallback timeoutCallback = pendingActions.remove(actionId);
            if (timeoutCallback != null) {
                Map<String, Object> result = new HashMap<>();
                result.put("success", false);
                timeoutCallback.onResult(result, "Action timed out");
            }
        }, 10000); // 10 second timeout

        // Get the MCPAccessibilityService instance
        MCPAccessibilityService service = MCPAccessibilityService.getInstance();
        // If we can directly access the service, use it
        try {
            service.executeAction(accessibilityActionType, parameters, (success, message) -> {
                // Create result object
                Map<String, Object> result = new HashMap<>();
                result.put("success", success);
                result.put("message", message);

                // Find and invoke the callback
                ActionResultCallback cb = pendingActions.remove(actionId);
                if (cb != null) {
                    cb.onResult(result, success ? null : message);
                }
            });
        } catch (Exception e) {
            Log.e(TAG, "Error calling accessibility service directly: " + e.getMessage());
        }
}

    /**
     * Map server action type to accessibility service action type
     */
    private String mapActionType(String actionType) {
        // Map action types if necessary
        switch (actionType) {
            case "click": return "CLICK";
            case "long_click": return "LONG_CLICK";
            case "swipe": return "SWIPE";
            case "type_text": return "TYPE_TEXT";
            case "scroll": return "SCROLL";
            case "launch_app": return "LAUNCH_APP";
            case "press_back": return "PRESS_BACK";
            case "press_home": return "PRESS_HOME";
            case "press_recents": return "PRESS_RECENTS";
            case "find_element": return "FIND_ELEMENT";
            case "get_text": return "GET_TEXT";
            case "get_ui_state": return "GET_UI_STATE";
            case "get_installed_apps": return "GET_INSTALLED_APPS";
            default: return actionType;
        }
    }

    /**
     * Handle UI state response
     */
    private void handleUIStateResponse(String uiStateJson) {
        try {
            JSONObject uiState = new JSONObject(uiStateJson);
            lastUIState = uiState;

            // Find matching action callback
            String actionId = "GET_UI_STATE_" + System.currentTimeMillis();
            ActionResultCallback callback = pendingActions.remove(actionId);
            if (callback != null) {
                Map<String, Object> result = new HashMap<>();
                result.put("uiState", uiState);
                result.put("success", true);
                callback.onResult(result, null);
            }
        } catch (JSONException e) {
            Log.e(TAG, "Error parsing UI state: " + e.getMessage());
        }
    }

    /**
     * Handle installed apps response
     */
    private void handleInstalledAppsResponse(String appsJson) {
        try {
            JSONArray apps = new JSONArray(appsJson);

            // Find matching action callback
            String actionId = "GET_INSTALLED_APPS_" + System.currentTimeMillis();
            ActionResultCallback callback = pendingActions.remove(actionId);
            if (callback != null) {
                Map<String, Object> result = new HashMap<>();
                result.put("installedApps", apps);
                result.put("success", true);
                callback.onResult(result, null);
            }
        } catch (JSONException e) {
            Log.e(TAG, "Error parsing installed apps: " + e.getMessage());
        }
    }

    /**
     * Handle element info response
     */
    private void handleElementInfoResponse(String elementInfoJson) {
        try {
            JSONObject elementInfo = new JSONObject(elementInfoJson);

            // Find matching action callback
            String actionId = "FIND_ELEMENT_" + System.currentTimeMillis();
            ActionResultCallback callback = pendingActions.remove(actionId);
            if (callback != null) {
                Map<String, Object> result = new HashMap<>();
                result.put("elementInfo", elementInfo);
                result.put("success", elementInfo.optBoolean("found", false));
                callback.onResult(result, null);
            }
        } catch (JSONException e) {
            Log.e(TAG, "Error parsing element info: " + e.getMessage());
        }
    }

    /**
     * Determine if device state should be included in response
     * @param actionType The action type
     * @return true if device state should be included
     */
    private boolean shouldIncludeDeviceState(String actionType) {
        // Include device state for UI-changing actions
        return actionType.equals("click") ||
                actionType.equals("long_click") ||
                actionType.equals("swipe") ||
                actionType.equals("scroll") ||
                actionType.equals("launch_app") ||
                actionType.equals("press_back") ||
                actionType.equals("press_home") ||
                actionType.equals("press_recents") ||
                actionType.equals("get_ui_state");
    }

    /**
     * Get current device state
     * @return JSONObject with device state
     */
    private JSONObject getDeviceState() {
        JSONObject deviceState = new JSONObject();
        try {
            // Get current package and activity
            deviceState.put("currentPackage", currentPackage);
            deviceState.put("currentActivity", currentActivity);

            // Get UI hierarchy if available
            if (lastUIState != null) {
                deviceState.put("uiHierarchy", lastUIState);
            }

            // For other state info, we could add additional broadcasts from the accessibility service

        } catch (JSONException e) {
            Log.e(TAG, "Error creating device state: " + e.getMessage());
        }

        return deviceState;
    }

    /**
     * Send a message to the server
     * @param message The message to send
     * @throws IOException if there's an error sending the message
     */
    private synchronized void sendMessage(JSONObject message) throws IOException {
        if (!isConnected || writer == null) {
            throw new IOException("Not connected to server");
        }

        String messageStr = message.toString() + "\n";
        Log.d(TAG, "Sending message: " + messageStr);

        try {
            writer.write(messageStr);
            writer.flush();
        } catch (IOException e) {
            Log.e(TAG, "Error sending message: " + e.getMessage());
            isConnected = false;
            throw e;
        }
    }

    /**
     * Send a request to the server
     * @param actionType The action type
     * @param parameters The parameters
     * @param callback The callback to handle the response
     */
    public void sendRequest(String actionType, Map<String, Object> parameters, RequestCallback callback) {
        if (!isConnected) {
            if (callback != null) {
                callback.onError("Not connected to server");
            }
            return;
        }

        executorService.execute(() -> {
            try {
                // Generate request ID
                String requestId = UUID.randomUUID().toString();

                // Create request message
                JSONObject requestMessage = new JSONObject();
                requestMessage.put("type", "request");
                requestMessage.put("requestId", requestId);
                requestMessage.put("actionType", actionType);

                // Add parameters
                JSONObject paramsObj = new JSONObject();
                if (parameters != null) {
                    for (Map.Entry<String, Object> entry : parameters.entrySet()) {
                        paramsObj.put(entry.getKey(), entry.getValue());
                    }
                }
                requestMessage.put("parameters", paramsObj);

                requestMessage.put("timestamp", System.currentTimeMillis() / 1000.0);

                // Register callback
                if (callback != null) {
                    pendingRequests.put(requestId, callback);

                    // Set timeout for request
                    mainHandler.postDelayed(() -> {
                        RequestCallback timeoutCallback = pendingRequests.remove(requestId);
                        if (timeoutCallback != null) {
                            timeoutCallback.onError("Request timed out");
                        }
                    }, 30000); // 30 second timeout
                }

                // Send request
                sendMessage(requestMessage);

            } catch (JSONException | IOException e) {
                Log.e(TAG, "Error sending request: " + e.getMessage());
                if (callback != null) {
                    callback.onError(e.getMessage());
                }
            }
        });
    }

    /**
     * Send an event to the server
     * @param eventType The event type
     * @param data The event data
     */
    public void sendEvent(String eventType, Map<String, Object> data) {
        if (!isConnected) {
            Log.w(TAG, "Cannot send event, not connected to server");
            return;
        }

        executorService.execute(() -> {
            try {
                // Create event message
                JSONObject eventMessage = new JSONObject();
                eventMessage.put("type", "event");
                eventMessage.put("eventType", eventType);
                eventMessage.put("deviceId", deviceId);

                // Add data
                if (data != null) {
                    for (Map.Entry<String, Object> entry : data.entrySet()) {
                        eventMessage.put(entry.getKey(), entry.getValue());
                    }
                }

                eventMessage.put("timestamp", System.currentTimeMillis() / 1000.0);

                // Send event
                sendMessage(eventMessage);

            } catch (JSONException | IOException e) {
                Log.e(TAG, "Error sending event: " + e.getMessage());
            }
        });
    }

    /**
     * Check if client is connected to server
     * @return true if connected
     */
    public boolean isConnected() {
        return isConnected;
    }

    /**
     * Get device ID
     * @return the device ID
     */
    private String getDeviceId() {
        return context.getSharedPreferences("mcp_prefs", Context.MODE_PRIVATE).getString("device_id", "unknown");
    }
}