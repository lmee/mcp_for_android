package com.jxev.ai;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

import com.jxev.ai.server.MCPAccessibilityService;

/**
 * 用于接收和转发操作动作的广播接收器
 * 这个类提供了一种在应用不同组件间传递操作指令的机制
 */
public class ActionBroadcastReceiver extends BroadcastReceiver {
    private static final String TAG = "ActionBroadcastReceiver";

    @Override
    public void onReceive(Context context, Intent intent) {
        if ("com.jxev.ai.ACTION_EXECUTE".equals(intent.getAction())) {
            Log.d(TAG, "收到操作执行广播");

            // 获取操作类型和参数
            String actionType = intent.getStringExtra("action_type");
            String actionParams = intent.getStringExtra("action_params");

            // 转发给无障碍服务
            Intent serviceIntent = new Intent(context, MCPAccessibilityService.class);
            serviceIntent.setAction("com.jxev.ai.ACTION_EXECUTE");
            serviceIntent.putExtra("action_type", actionType);
            serviceIntent.putExtra("action_params", actionParams);

            // 使用有序广播确保操作顺序执行
            context.sendOrderedBroadcast(serviceIntent, null);

            Log.d(TAG, "已转发操作: " + actionType);
        }
    }
}