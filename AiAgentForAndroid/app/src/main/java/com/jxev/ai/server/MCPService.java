package com.jxev.ai.server;

import android.app.Service;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.os.Binder;
import android.os.IBinder;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

public class MCPService extends Service {
    private static final String TAG = "MCPService";
    private static final String SERVER_URL = "http://192.168.0.25:5000/"; // 更改为您的服务器地址

    private final IBinder binder = new LocalBinder();
    private OkHttpClient httpClient;
    private ExecutorService executorService;
    private StatusCallback statusCallback;

    // 设备能力列表
    private final List<String> deviceCapabilities = new ArrayList<>();

    public interface StatusCallback {
        void onStatusUpdate(String status);
    }

    @Override
    public void onCreate() {
        super.onCreate();
        Log.e("Jerry","MCP Service start");
        httpClient = new OkHttpClient();
        executorService = Executors.newCachedThreadPool();

        // 初始化设备能力列表
        initializeCapabilities();
    }

    private void initializeCapabilities() {
        deviceCapabilities.add("open_app");
        deviceCapabilities.add("click");
        deviceCapabilities.add("input_text");
        deviceCapabilities.add("scroll");
        deviceCapabilities.add("long_press");
        deviceCapabilities.add("back");
        deviceCapabilities.add("home");
        // 新增的自学习相关能力
        deviceCapabilities.add("get_installed_apps");
        deviceCapabilities.add("get_ui_state");
        deviceCapabilities.add("launch_app");
    }

    public void setStatusCallback(StatusCallback callback) {
        this.statusCallback = callback;
    }

    public void updateStatus(String status) {
        if (statusCallback != null) {
            statusCallback.onStatusUpdate(status);
        }
    }

    public void registerDevice(final String deviceId) {
        executorService.execute(() -> {
            try {
                JSONObject requestData = new JSONObject();
                requestData.put("device_id", deviceId);

                JSONArray capabilities = new JSONArray();
                for (String capability : deviceCapabilities) {
                    capabilities.put(capability);
                }
                requestData.put("capabilities", capabilities);

                String requestBody = requestData.toString();

                Request request = new Request.Builder()
                        .url(SERVER_URL + "/register_device")
                        .post(RequestBody.create(
                                MediaType.parse("application/json"), requestBody))
                        .build();

                httpClient.newCall(request).enqueue(new Callback() {
                    @Override
                    public void onFailure(@NonNull Call call, IOException e) {
                        updateStatus("设备注册失败: " + e.getMessage());
                        Log.e(TAG, "设备注册失败", e);
                    }

                    @Override
                    public void onResponse(@NonNull Call call, @NonNull Response response) throws IOException {
                        if (response.isSuccessful()) {
                            updateStatus("设备已注册并准备就绪");
                            Log.d(TAG, "设备注册成功");
                        } else {
                            updateStatus("设备注册失败: " + response.code());
                            Log.e(TAG, "设备注册失败: " + response.code());
                        }
                    }
                });
            } catch (JSONException e) {
                updateStatus("设备注册错误: " + e.getMessage());
                Log.e(TAG, "JSON错误", e);
            }
        });
    }

    public void executeCommand(final String command) {
        // 首先更新UI状态
        updateStatus("正在处理指令: " + command);

        executorService.execute(() -> {
            try {
                JSONObject requestData = new JSONObject();
                requestData.put("device_id", getDeviceId());
                requestData.put("command", command);

                String requestBody = requestData.toString();

                Request request = new Request.Builder()
                        .url(SERVER_URL + "/execute")
                        .post(RequestBody.create(
                                MediaType.parse("application/json"), requestBody))
                        .build();

                httpClient.newCall(request).enqueue(new Callback() {
                    @Override
                    public void onFailure(Call call, IOException e) {
                        updateStatus("指令执行失败: " + e.getMessage());
                        Log.e(TAG, "指令执行失败", e);
                    }

                    @Override
                    public void onResponse(@NonNull Call call, @NonNull Response response) throws IOException {
                        if (response.isSuccessful()) {
                            try {
                                String responseBody = response.body().string();
                                JSONObject jsonResponse = new JSONObject(responseBody);

                                String status = jsonResponse.getString("status");
                                String message = jsonResponse.getString("message");

                                if ("success".equals(status)) {
                                    updateStatus("正在执行: " + message);

                                    // 获取动作序列并执行
                                    JSONArray actionsArray = jsonResponse.getJSONArray("actions");
                                    executeActions(actionsArray);
                                } else {
                                    updateStatus(message);
                                }
                            } catch (JSONException e) {
                                updateStatus("解析响应失败: " + e.getMessage());
                                Log.e(TAG, "JSON解析错误", e);
                            }
                        } else {
                            updateStatus("指令执行失败: " + response.code());
                            Log.e(TAG, "服务器错误: " + response.code());
                        }
                    }
                });
            } catch (JSONException e) {
                updateStatus("指令执行错误: " + e.getMessage());
                Log.e(TAG, "JSON错误", e);
            }
        });
    }

    /**
     * 学习应用
     */
    public void learnApps() {
        updateStatus("开始学习设备上的应用...");

        executorService.execute(() -> {
            try {
                // 先尝试获取已安装应用列表
                List<Map<String, String>> installedApps = getInstalledApps();

                // 向服务器发送学习请求
                JSONObject requestData = new JSONObject();
                Log.e("Jerry","-->"+getDeviceId());
                requestData.put("device_id", getDeviceId());
//                requestData.put("package_name","com.android.bbkmusic");

                String requestBody = requestData.toString();

                Request request = new Request.Builder()
                        .url(SERVER_URL + "/learn_app")
                        .post(RequestBody.create(
                                MediaType.parse("application/json"), requestBody))
                        .build();

                httpClient.newCall(request).enqueue(new Callback() {
                    @Override
                    public void onFailure(@NonNull Call call, IOException e) {
                        updateStatus("学习应用失败: " + e.getMessage());
                        Log.e(TAG, "学习应用失败", e);
                    }

                    @Override
                    public void onResponse(@NonNull Call call, @NonNull Response response) throws IOException {
                        if (response.isSuccessful()) {
                            try {
                                String responseBody = response.body().string();
                                JSONObject jsonResponse = new JSONObject(responseBody);

                                String status = jsonResponse.getString("status");
                                String message = jsonResponse.getString("message");

                                if ("success".equals(status)) {
                                    String sessionId = jsonResponse.getString("session_id");
                                    updateStatus("应用学习会话开始: " + message + " (会话ID: " + sessionId + ")");
                                } else {
                                    updateStatus("应用学习失败: " + message);
                                }
                            } catch (JSONException e) {
                                updateStatus("解析响应失败: " + e.getMessage());
                                Log.e(TAG, "JSON解析错误", e);
                            }
                        } else {
                            updateStatus("应用学习请求失败: " + response.code());
                            Log.e(TAG, "服务器错误: " + response.code());
                        }
                    }
                });
            } catch (Exception e) {
                updateStatus("学习应用错误: " + e.getMessage());
                Log.e(TAG, "错误", e);
            }
        });
    }

    /**
     * 学习特定应用
     */
    public void learnApp(final String packageName) {
        if (packageName == null || packageName.isEmpty()) {
            updateStatus("未指定应用包名");
            return;
        }

        updateStatus("开始学习应用: " + packageName);

        executorService.execute(() -> {
            try {
                JSONObject requestData = new JSONObject();
                requestData.put("device_id", getDeviceId());
                requestData.put("package_name", packageName);

                String requestBody = requestData.toString();

                Request request = new Request.Builder()
                        .url(SERVER_URL + "/learn_app")
                        .post(RequestBody.create(
                                MediaType.parse("application/json"), requestBody))
                        .build();

                httpClient.newCall(request).enqueue(new Callback() {
                    @Override
                    public void onFailure(@NonNull Call call, @NonNull IOException e) {
                        updateStatus("学习应用失败: " + e.getMessage());
                        Log.e(TAG, "学习应用失败", e);
                    }

                    @Override
                    public void onResponse(@NonNull Call call, @NonNull Response response) throws IOException {
                        if (response.isSuccessful()) {
                            try {
                                String responseBody = response.body().string();
                                JSONObject jsonResponse = new JSONObject(responseBody);

                                String status = jsonResponse.getString("status");
                                String message = jsonResponse.getString("message");

                                if ("success".equals(status)) {
                                    String sessionId = jsonResponse.getString("session_id");
                                    updateStatus("应用学习已开始: " + message);
                                } else {
                                    updateStatus("应用学习失败: " + message);
                                }
                            } catch (JSONException e) {
                                updateStatus("解析响应失败: " + e.getMessage());
                                Log.e(TAG, "JSON解析错误", e);
                            }
                        } else {
                            updateStatus("应用学习请求失败: " + response.code());
                            Log.e(TAG, "服务器错误: " + response.code());
                        }
                    }
                });
            } catch (JSONException e) {
                updateStatus("学习应用错误: " + e.getMessage());
                Log.e(TAG, "JSON错误", e);
            }
        });
    }

    /**
     * 获取已安装应用列表
     */
    private List<Map<String, String>> getInstalledApps() {
        List<Map<String, String>> result = new ArrayList<>();

        PackageManager pm = getPackageManager();
        List<ApplicationInfo> apps = pm.getInstalledApplications(PackageManager.GET_META_DATA);

        for (ApplicationInfo app : apps) {
            // 仅包含有启动意图的应用
            if (pm.getLaunchIntentForPackage(app.packageName) != null) {
                Map<String, String> appInfo = new HashMap<>();
                appInfo.put("packageName", app.packageName);
                appInfo.put("appName", pm.getApplicationLabel(app).toString());
                result.add(appInfo);
            }
        }

        return result;
    }

    private void executeActions(JSONArray actionsArray) throws JSONException {
        // 将动作发送到无障碍服务执行
        for (int i = 0; i < actionsArray.length(); i++) {
            JSONObject action = actionsArray.getJSONObject(i);
            String actionType = action.getString("action");
            JSONObject params = action.optJSONObject("params");
            if (params == null) {
                params = new JSONObject();
            }

            // 创建Intent发送给无障碍服务
            Intent actionIntent = new Intent(this, MCPAccessibilityService.class);
            actionIntent.setAction("com.jxev.ai.ACTION_EXECUTE");
            actionIntent.putExtra("action_type", actionType);
            actionIntent.putExtra("action_params", params.toString());
            sendBroadcast(actionIntent);

            // 等待一小段时间以确保动作顺序
            if ("wait".equals(actionType)) {
                try {
                    int milliseconds = params.getInt("milliseconds");
                    Thread.sleep(milliseconds);
                } catch (InterruptedException e) {
                    Log.e(TAG, "等待中断", e);
                }
            } else {
                try {
                    // 默认等待时间，确保动作完成
                    Thread.sleep(500);
                } catch (InterruptedException e) {
                    Log.e(TAG, "等待中断", e);
                }
            }
        }

        updateStatus("指令执行完成");
    }

    private String getDeviceId() {
        return getSharedPreferences("mcp_prefs", MODE_PRIVATE).getString("device_id", "unknown");
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return binder;
    }

    public class LocalBinder extends Binder {
        public MCPService getService() {
            return MCPService.this;
        }
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        executorService.shutdown();
    }
}