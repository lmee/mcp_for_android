package com.jxev.ai;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.os.Bundle;
import android.os.IBinder;
import android.provider.Settings;
import android.util.Log;
import android.view.View;
import android.view.accessibility.AccessibilityManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.jxev.ai.client.MCPSocketClient;
import com.jxev.ai.server.MCPService;

import java.util.List;
import java.util.UUID;


public class MainActivity extends AppCompatActivity {

    private static final String TAG = "MainActivity";
    private static final int REQUEST_ACCESSIBILITY = 1001;
    private MCPSocketClient socketClient;
    private TextView statusTextView;
    private EditText commandEditText;
    private Button executeButton;
    private Button learnAppsButton;
    private MCPService mcpService;
    private boolean isBound = false;
    // MCP client
    private MCPSocketClient mcpClient;
    private String deviceId;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // 生成设备ID
        deviceId = getDeviceId();

        // 初始化UI组件
        statusTextView = findViewById(R.id.statusTextView);
        commandEditText = findViewById(R.id.commandEditText);
        executeButton = findViewById(R.id.executeButton);
        learnAppsButton = findViewById(R.id.learnAppsButton);

        // 检查无障碍服务权限
        checkAccessibilityPermission();

        // 启动并绑定服务
        Intent serviceIntent = new Intent(this, MCPService.class);
        startService(serviceIntent);
        bindService(serviceIntent, serviceConnection, Context.BIND_AUTO_CREATE);

        // 设置执行按钮点击事件
        executeButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                String command = commandEditText.getText().toString().trim();
                if (!command.isEmpty() && mcpService != null) {
                    mcpService.executeCommand(command);
                    commandEditText.setText("");
                }
            }
        });

        // 设置学习应用按钮点击事件
        learnAppsButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (mcpService != null) {
                    mcpService.learnApps();
                    updateStatus("正在学习设备上的应用...");
                }
            }
        });

        mcpClient = new MCPSocketClient(getApplicationContext(), "192.168.0.25", 8080);

        // Set connection callback
        mcpClient.setConnectionCallback(new MCPSocketClient.ConnectionCallback() {
            @Override
            public void onConnected() {
                runOnUiThread(() -> {
                    Log.d("Jerry","Socket connect");
//                    statusText.setText("Connected to " + host + ":" + port);
//                    connectButton.setText("Disconnect");
//                    connectButton.setEnabled(true);
                });
            }

            @Override
            public void onDisconnected(String reason) {
                runOnUiThread(() -> {
                    Log.d("Jerry","Socket disconnect");
//                    statusText.setText("Disconnected: " + reason);
//                    connectButton.setText("Connect");
//                    connectButton.setEnabled(true);
                });
            }

            @Override
            public void onConnectionFailed(String error) {
                runOnUiThread(() -> {
//                    statusText.setText("Connection failed: " + error);
//                    connectButton.setText("Connect");
//                    connectButton.setEnabled(true);
                });
            }
        });
        mcpClient.connect();
    }

    private String getDeviceId() {
        // 获取或生成一个唯一的设备ID
        String savedId = getSharedPreferences("mcp_prefs", MODE_PRIVATE).getString("device_id", null);
        if (savedId == null) {
            savedId = UUID.randomUUID().toString();
            getSharedPreferences("mcp_prefs", MODE_PRIVATE).edit().putString("device_id", savedId).apply();
        }
        return savedId;
    }

    private void updateStatus(String status) {
        runOnUiThread(() -> statusTextView.setText(status));
    }

    private void checkAccessibilityPermission() {
        if (!isAccessibilityServiceEnabled()) {
            statusTextView.setText("请启用无障碍服务");
            Toast.makeText(this, "请前往设置启用MCP无障碍服务", Toast.LENGTH_LONG).show();
            startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
        }
    }

    private boolean isAccessibilityServiceEnabled() {
        // 检查无障碍服务是否启用的逻辑
        AccessibilityManager am = (AccessibilityManager) getSystemService(Context.ACCESSIBILITY_SERVICE);
        List<AccessibilityServiceInfo> enabledServices = am.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK);
        for (AccessibilityServiceInfo serviceInfo : enabledServices) {
            if (serviceInfo.getId().contains(getPackageName())) {
                return true;
            }
        }
        return false;
    }


    private final ServiceConnection serviceConnection = new ServiceConnection() {
        @Override
        public void onServiceConnected(ComponentName name, IBinder service) {
            MCPService.LocalBinder binder = (MCPService.LocalBinder) service;
            mcpService = binder.getService();
            isBound = true;

            // 设置状态更新回调
            mcpService.setStatusCallback(new MCPService.StatusCallback() {
                @Override
                public void onStatusUpdate(final String status) {
                    runOnUiThread(() -> statusTextView.setText(status));
                }
            });

            // 服务连接后注册设备
            mcpService.registerDevice(deviceId);

            Log.d(TAG, "Service connected");
        }

        @Override
        public void onServiceDisconnected(ComponentName name) {
            mcpService = null;
            isBound = false;
            Log.d(TAG, "Service disconnected");
        }
    };

    @Override
    protected void onDestroy() {
        super.onDestroy();
//        mcpClient.disconnect();
//        if (isBound) {
//            unbindService(serviceConnection);
//            isBound = false;
//        }
    }
}