package com.jxev.ai.server;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.accessibilityservice.GestureDescription;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.graphics.Path;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.Log;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * MCP无障碍服务
 * 用于执行自动化操作，包括点击、滚动、输入等，支持MCP模型上下文协议
 */
public class MCPAccessibilityService extends AccessibilityService {
    private static final String TAG = "MCPAccessibilityService";

    // 当前应用包名
    private String currentPackage;

    // 当前活动名称
    private String currentActivity;

    // 是否正在记录操作
    private boolean isRecording = false;

    // 记录的操作序列
    private final List<Map<String, Object>> recordedActions = new ArrayList<>();

    // 操作处理历史
    private final Map<String, Long> actionHistory = new ConcurrentHashMap<>();

    // 处理程序（主线程）
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    // 上次UI状态
    private String lastUiStateHash = "";

    // 服务是否已连接
    private boolean isServiceConnected = false;

    // 单例实例
    private static MCPAccessibilityService instance;

    /**
     * 动作回调接口
     */
    public interface ActionCallback {
        void onResult(boolean success, String message);
    }


    /**
     * 获取服务实例（单例模式）
     */
    public static MCPAccessibilityService getInstance() {
        return instance;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        Log.d(TAG, "无障碍服务已创建");
        instance = this;
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        Log.d(TAG, "无障碍服务已销毁");

        // 清除单例引用
        if (instance == this) {
            instance = null;
        }
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        try {
            // 获取事件类型
            int eventType = event.getEventType();

            // 更新当前包名和活动名称
            if (eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
                if (event.getPackageName() != null) {
                    currentPackage = event.getPackageName().toString();
                }

                if (event.getClassName() != null) {
                    currentActivity = event.getClassName().toString();
                }

                Log.d(TAG, "当前应用: " + currentPackage + ", 活动: " + currentActivity);

                // 发送UI改变通知
                sendUiChangedEvent();
            }

            // 如果正在记录，记录用户操作
            if (isRecording) {
                recordAction(event);
            }
        } catch (Exception e) {
            Log.e(TAG, "处理无障碍事件错误", e);
        }
    }

    @Override
    public void onInterrupt() {
        Log.e(TAG, "无障碍服务被中断");
    }

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        Log.d(TAG, "无障碍服务已连接");
//        isServiceConnected = true;
//
//        // 配置服务信息
//        AccessibilityServiceInfo info = getServiceInfo();
//        if (info != null) {
//            // 设置需要监听的事件类型
//            info.eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED |
//                    AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED |
//                    AccessibilityEvent.TYPE_VIEW_CLICKED |
//                    AccessibilityEvent.TYPE_VIEW_LONG_CLICKED |
//                    AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED |
//                    AccessibilityEvent.TYPE_VIEW_SCROLLED;
//
//            // 设置反馈类型
//            info.feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC;
//
//            // 设置超时
//            info.notificationTimeout = 100;
//
//            // 请求额外功能
//            info.flags = AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS |
//                    AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS |
//                    AccessibilityServiceInfo.FLAG_REQUEST_TOUCH_EXPLORATION_MODE |
//                    AccessibilityServiceInfo.FLAG_REQUEST_ENHANCED_WEB_ACCESSIBILITY;
//
//            // 应用配置
//            setServiceInfo(info);
//        }
    }

    /**
     * 发送当前包信息
     */
    private void sendCurrentPackageInfo() {
        Intent intent = new Intent("com.jxev.ai.CURRENT_PACKAGE");
        intent.putExtra("package_name", currentPackage);
        intent.putExtra("activity_name", currentActivity);
        sendBroadcast(intent);
    }

    /**
     * 发送UI改变事件
     */
    /**
     * 发送UI改变事件 - 使用MCP协议结构
     */
    private void sendUiChangedEvent() {
        Log.d(TAG, "发送UI改变事件");
        // 获取当前UI状态
        AccessibilityNodeInfo rootNode = getRootInActiveWindow();
        if (rootNode == null) return;

        try {
            // 生成UI状态哈希值
            String uiHash = generateUiHash(rootNode);

            // 如果UI状态没有变化，跳过
            if (uiHash.equals(lastUiStateHash)) {
                return;
            }

            lastUiStateHash = uiHash;

            // 创建符合MCP协议的设备状态
            Map<String, Object> deviceState = new HashMap<>();
            deviceState.put("current_package", currentPackage);
            deviceState.put("current_activity", currentActivity);
            deviceState.put("screen_state", isScreenOn() ? "on" : "off");

            // 提取可见文本
            deviceState.put("visible_text", extractVisibleTexts(rootNode));

            // 简化UI层次结构，只获取交互元素
            List<AccessibilityNodeInfo> interactiveNodes = findInteractiveNodes(rootNode);
            Map<String, Object> simplifiedHierarchy = new HashMap<>();
            List<Map<String, Object>> elements = new ArrayList<>();

            for (AccessibilityNodeInfo node : interactiveNodes) {
                elements.add(getNodeInfo(node));
                node.recycle();
            }

            simplifiedHierarchy.put("elements", elements);
            deviceState.put("ui_hierarchy", simplifiedHierarchy);

            // 添加设备信息
            deviceState.put("device_info", getDeviceInfo());

            // 发送UI状态事件
            Intent intent = new Intent("com.jxev.ai.UI_CHANGED");
            intent.putExtra("device_state", new JSONObject(deviceState).toString());
            sendBroadcast(intent);

        } catch (Exception e) {
            Log.e(TAG, "发送UI改变事件出错", e);
        } finally {
            rootNode.recycle();
        }
    }

    /**
     * 生成UI状态哈希值
     */
    private String generateUiHash(AccessibilityNodeInfo rootNode) {
        if (rootNode == null) return "";

        StringBuilder sb = new StringBuilder();
        sb.append(currentPackage).append("|").append(currentActivity).append("|");

        List<AccessibilityNodeInfo> interactiveNodes = findInteractiveNodes(rootNode);
        for (AccessibilityNodeInfo node : interactiveNodes) {
            sb.append(nodeToString(node)).append(";");
        }

        for (AccessibilityNodeInfo node : interactiveNodes) {
            node.recycle();
        }

        return sb.toString().hashCode() + "";
    }

    /**
     * 将节点转为字符串
     */
    private String nodeToString(AccessibilityNodeInfo node) {
        if (node == null) return "";

        StringBuilder sb = new StringBuilder();

        // 基本信息
        CharSequence text = node.getText();
        CharSequence desc = node.getContentDescription();
        String id = node.getViewIdResourceName();
        CharSequence className = node.getClassName();

        sb.append(text != null ? text : "").append("|");
        sb.append(desc != null ? desc : "").append("|");
        sb.append(id != null ? id : "").append("|");
        sb.append(className != null ? className : "").append("|");

        // 位置信息
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        sb.append(bounds.left).append(",").append(bounds.top).append(",")
                .append(bounds.right).append(",").append(bounds.bottom);

        return sb.toString();
    }

    /**
     * 查找交互节点
     */
    private List<AccessibilityNodeInfo> findInteractiveNodes(AccessibilityNodeInfo rootNode) {
        List<AccessibilityNodeInfo> results = new ArrayList<>();
        if (rootNode == null) return results;

        // 递归查找
        findInteractiveNodesRecursive(rootNode, results);

        return results;
    }

    /**
     * 递归查找交互节点
     */
    private void findInteractiveNodesRecursive(AccessibilityNodeInfo node, List<AccessibilityNodeInfo> results) {
        if (node == null) return;

        // 检查节点是否是交互元素
        if (isInteractiveNode(node)) {
            results.add(AccessibilityNodeInfo.obtain(node));
        }

        // 递归子节点
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                findInteractiveNodesRecursive(child, results);
                child.recycle();
            }
        }
    }

    /**
     * 判断节点是否是交互元素
     */
    private boolean isInteractiveNode(AccessibilityNodeInfo node) {
        if (node == null) return false;

        // 可点击、可长按或可聚焦
        boolean isInteractive = node.isClickable() || node.isLongClickable() || node.isFocusable();

        // 有文本或内容描述的节点
        if (!isInteractive) {
            CharSequence text = node.getText();
            CharSequence desc = node.getContentDescription();
            isInteractive = (text != null && !text.toString().isEmpty()) ||
                    (desc != null && !desc.toString().isEmpty());
        }

        return isInteractive;
    }

    /**
     * 提取可见文本
     */
    private List<Map<String, Object>> extractVisibleTexts(AccessibilityNodeInfo rootNode) {
        List<Map<String, Object>> results = new ArrayList<>();
        if (rootNode == null) return results;

        List<AccessibilityNodeInfo> textNodes = new ArrayList<>();
        findTextNodes(rootNode, textNodes);

        for (AccessibilityNodeInfo node : textNodes) {
            CharSequence text = node.getText();
            if (text != null && !text.toString().isEmpty()) {
                Map<String, Object> textElement = new HashMap<>();

                // TextElement 结构: text, element_type, attributes, bounds
                textElement.put("text", text.toString());

                // 获取元素类型
                CharSequence className = node.getClassName();
                textElement.put("element_type", className != null ? className.toString() : "unknown");

                // 获取属性
                Map<String, String> attributes = new HashMap<>();
                String id = node.getViewIdResourceName();
                if (id != null) attributes.put("id", id);

                CharSequence desc = node.getContentDescription();
                if (desc != null) attributes.put("description", desc.toString());

                attributes.put("clickable", String.valueOf(node.isClickable()));
                attributes.put("enabled", String.valueOf(node.isEnabled()));
                textElement.put("attributes", attributes);

                // 获取位置
                Rect bounds = new Rect();
                node.getBoundsInScreen(bounds);
                Map<String, Integer> boundsMap = new HashMap<>();
                boundsMap.put("left", bounds.left);
                boundsMap.put("top", bounds.top);
                boundsMap.put("right", bounds.right);
                boundsMap.put("bottom", bounds.bottom);
                textElement.put("bounds", boundsMap);

                results.add(textElement);
            }
            node.recycle();
        }

        return results;
    }

    /**
     * 查找文本节点
     */
    private void findTextNodes(AccessibilityNodeInfo node, List<AccessibilityNodeInfo> results) {
        if (node == null) return;

        CharSequence text = node.getText();
        if (text != null && !text.toString().isEmpty()) {
            results.add(AccessibilityNodeInfo.obtain(node));
        }

        // 递归子节点
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                findTextNodes(child, results);
                child.recycle();
            }
        }
    }

    /**
     * 开始记录操作
     */
    private void startRecording() {
        isRecording = true;
        recordedActions.clear();
        Log.d(TAG, "开始记录操作");

        // 通知记录已开始
        Intent intent = new Intent("com.jxev.ai.RECORDING_STARTED");
        sendBroadcast(intent);
    }

    /**
     * 停止记录操作
     */
    private void stopRecording() {
        isRecording = false;

        Log.d(TAG, "停止记录操作，共记录 " + recordedActions.size() + " 个操作");

        // 向服务发送记录的操作
        Intent intent = new Intent("com.jxev.ai.RECORDED_ACTIONS");
        JSONArray actionsArray = new JSONArray();
        for (Map<String, Object> action : recordedActions) {
            actionsArray.put(new JSONObject(action));
        }
        intent.putExtra("actions_json", actionsArray.toString());
        sendBroadcast(intent);
    }

    /**
     * 记录用户操作
     */
    private void recordAction(AccessibilityEvent event) {
        Map<String, Object> action = new HashMap<>();

        switch (event.getEventType()) {
            case AccessibilityEvent.TYPE_VIEW_CLICKED:
                action.put("action", "click");

                AccessibilityNodeInfo source = event.getSource();
                if (source != null) {
                    Map<String, Object> params = new HashMap<>();

                    // 尝试获取各种标识符
                    CharSequence text = source.getText();
                    CharSequence desc = source.getContentDescription();
                    String id = source.getViewIdResourceName();

                    if (id != null) {
                        params.put("id", id);
                    } else if (text != null && !text.toString().isEmpty()) {
                        params.put("text", text.toString());
                    } else if (desc != null && !desc.toString().isEmpty()) {
                        params.put("desc", desc.toString());
                    }

                    // 添加坐标信息
                    Rect bounds = new Rect();
                    source.getBoundsInScreen(bounds);
                    params.put("x", bounds.centerX());
                    params.put("y", bounds.centerY());

                    action.put("params", params);
                    recordedActions.add(action);

                    source.recycle();
                }
                break;

            case AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED:
                action.put("action", "type_text");

                AccessibilityNodeInfo textSource = event.getSource();
                if (textSource != null) {
                    Map<String, Object> params = new HashMap<>();

                    String id = textSource.getViewIdResourceName();
                    CharSequence text = textSource.getText();

                    if (id != null) {
                        params.put("id", id);
                    }

                    if (text != null) {
                        params.put("text", text.toString());
                    }

                    action.put("params", params);
                    recordedActions.add(action);

                    textSource.recycle();
                }
                break;

            case AccessibilityEvent.TYPE_VIEW_SCROLLED:
                action.put("action", "scroll");
                Map<String, Object> params = new HashMap<>();
                params.put("direction", "down"); // 简化版，实际应该检测方向
                action.put("params", params);
                recordedActions.add(action);
                break;

            // 可以添加更多事件类型的处理
            case AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED:
                // 内容变化事件，通常比较频繁，只有在特定情况下记录
                if (event.getSource() != null && isSignificantContentChange(event)) {
                    action.put("action", "content_change");
                    action.put("params", new HashMap<>());
                    recordedActions.add(action);
                }
                break;
        }
    }

    /**
     * 判断是否是重要的内容变化
     */
    private boolean isSignificantContentChange(AccessibilityEvent event) {
        // 这里可以实现更复杂的判断逻辑
        // 简化实现，只在父节点内容变化时记录
        return event.getSource() != null &&
                event.getSource().getChildCount() > 0;
    }

    /**
     * 执行操作 (Original method, kept for backward compatibility)
     */
    public void executeAction(String actionType, JSONObject params) {
        executeAction(actionType, params, null);
    }
    /**
     * 执行操作
     */
    public void executeAction(String actionType, JSONObject params, ActionCallback callback) {
        try {
            // For each current actionType, we'll use the existing implementation
            // but add a callback call at the end
            Log.d(TAG,"检查无障碍服务是否已正常启动"+isAccessibilityServiceEnabled());
            Log.d(TAG, "执行动作: " + actionType + ", 参数: " + params);
            boolean success = false;
            String message = "";

            // 为每个动作生成唯一标识
            String actionId = actionType + "_" + System.currentTimeMillis();

            // 如果是启动应用操作，先重置所有动作历史
            if ("launch_app".equalsIgnoreCase(actionType) || "LAUNCH_APP".equalsIgnoreCase(actionType)) {
                resetAllActionHistory();
            }
            // 其他动作正常检查是否在进行中
            else if (isActionInProgress(actionId)) {
                Log.d(TAG, "动作正在执行，忽略重复请求: " + actionType);
                if (callback != null) {
                    callback.onResult(false, "动作正在执行，忽略重复请求");
                }
                return;
            }

            // 记录动作开始执行
            recordActionStart(actionId);

            switch (actionType) {
                case "click":
                case "CLICK":
                    if (params.has("selector")) {
                        success = clickNodeBySelector(params.getString("selector"));
                        message = success ? "点击成功" : "点击失败";
                    } else if (params.has("id")) {
                        success = clickNodeById(params.getString("id"));
                        message = success ? "点击成功" : "点击失败";
                    } else if (params.has("text")) {
                        success = clickNodeByText(params.getString("text"));
                        message = success ? "点击成功" : "点击失败";
                    } else if (params.has("desc")) {
                        success = clickNodeByText(params.getString("desc"));
                        message = success ? "点击成功" : "点击失败";
                    } else if (params.has("x") && params.has("y")) {
                        clickAtCoordinates(params.getInt("x"), params.getInt("y"));
                        // For coordinate clicks, we don't immediately know the success
                        // We'll rely on notifyActionResult to be called from gesture callback
                        recordActionComplete(actionId);
                        return; // Early return since callback will be called by gesture handler
                    } else {
                        success = false;
                        message = "缺少选择器、ID、文本或坐标";
                    }
                    break;

                case "input_text":
                case "TYPE_TEXT":
                    String selector = params.optString("selector", null);
                    String text = params.getString("text");
                    if (selector != null) {
                        success = inputTextBySelector(selector, text);
                        message = success ? "文本输入成功" : "文本输入失败";
                    } else {
                        String id = params.optString("id", null);
                        if (id != null) {
                            success = inputText(id, text);
                            message = success ? "文本输入成功" : "文本输入失败";
                        } else {
                            success = false;
                            message = "缺少选择器或ID";
                        }
                    }
                    break;

                case "scroll":
                case "SCROLL":
                    boolean isDown = params.optBoolean("down", true);
                    success = performScroll(isDown);
                    message = success ? "滚动成功" : "滚动失败";
                    break;

                case "long_press":
                case "LONG_CLICK":
                    if (params.has("selector")) {
                        success = longPressNodeBySelector(params.getString("selector"));
                        message = success ? "长按成功" : "长按失败";
                    } else if (params.has("id")) {
                        success = longPressNodeById(params.getString("id"));
                        message = success ? "长按成功" : "长按失败";
                    } else if (params.has("text")) {
                        success = longPressNodeByText(params.getString("text"));
                        message = success ? "长按成功" : "长按失败";
                    } else if (params.has("x") && params.has("y")) {
                        longPressAtCoordinates(params.getInt("x"), params.getInt("y"));
                        // For coordinate presses, we don't immediately know the success
                        recordActionComplete(actionId);
                        return; // Early return
                    } else {
                        success = false;
                        message = "缺少选择器、ID、文本或坐标";
                    }
                    break;

                case "back":
                case "PRESS_BACK":
                    success = performGlobalAction(GLOBAL_ACTION_BACK);
                    message = success ? "返回成功" : "返回失败";
                    break;

                case "home":
                case "PRESS_HOME":
                    success = performGlobalAction(GLOBAL_ACTION_HOME);
                    message = success ? "返回主屏幕成功" : "返回主屏幕失败";
                    break;

                case "launch_app":
                case "LAUNCH_APP":
                    success = launchApp(params.getString("packageName"));
                    message = success ? "启动应用成功" : "启动应用失败";
                    break;

                case "swipe":
                case "SWIPE":
                    int x1 = params.getInt("x1");
                    int y1 = params.getInt("y1");
                    int x2 = params.getInt("x2");
                    int y2 = params.getInt("y2");
                    int duration = params.optInt("duration", 300);
                    performSwipe(x1, y1, x2, y2, duration);
                    // For swipes, we don't immediately know the success
                    recordActionComplete(actionId);
                    return; // Early return

                case "get_ui_state":
                case "GET_UI_STATE":
                    // 捕获UI状态并发送
                    Thread.sleep(600);
                    message = getAndSendUIState();
                    success = !TextUtils.isEmpty(message);
                    recordActionComplete(actionId);
                    break; // Early return

                case "get_installed_apps":
                case "GET_INSTALLED_APPS":
                    // 获取已安装应用列表并发送
                    message = getAndSendInstalledApps();
                    success = !TextUtils.isEmpty(message);
                    recordActionComplete(actionId);
                    break;
                case "find_element":
                case "FIND_ELEMENT":
                    // 查找元素并返回相关信息
                    findAndReportElement(params.getString("selector"));
                    recordActionComplete(actionId);
                    return; // Early return

                case "focus":
                case "FOCUS":
                    // 聚焦元素
                    if (params.has("selector")) {
                        success = focusOnElement(params.getString("selector"));
                        message = success ? "聚焦成功" : "聚焦失败";
                    } else {
                        success = false;
                        message = "缺少选择器参数";
                    }
                    break;

                case "press_recents":
                case "PRESS_RECENTS":
                    // 显示最近任务
                    success = performGlobalAction(GLOBAL_ACTION_RECENTS);
                    message = success ? "显示最近任务成功" : "显示最近任务失败";
                    break;

                case "press_notifications":
                case "PRESS_NOTIFICATIONS":
                    // 打开通知栏
                    success = performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS);
                    message = success ? "打开通知栏成功" : "打开通知栏失败";
                    break;

                case "wait":
                case "WAIT":
                    // 等待指定时间
                    int milliseconds = params.optInt("milliseconds", 500);
                    Thread.sleep(milliseconds);
                    success = true;
                    message = "等待" + milliseconds + "毫秒完成";
                    break;

                default:
                    Log.w(TAG, "未知动作类型: " + actionType);
                    success = false;
                    message = "未知动作类型";
                    break;
            }

            // 记录动作完成
            recordActionComplete(actionId);

            // 通知结果
            notifyActionResult(actionType, success, message);

            // 调用回调（如果有）
            if (callback != null) {
                callback.onResult(success, message);
            }

        } catch (Exception e) {
            Log.e(TAG, "执行动作错误: " + actionType, e);
            notifyActionResult(actionType, false, "执行错误: " + e.getMessage());
            if (callback != null) {
                callback.onResult(false, "执行错误: " + e.getMessage());
            }
        }
    }

    /**
     * 重置所有动作历史记录
     */
    private void resetAllActionHistory() {
        Log.d(TAG, "重置所有动作历史，清除 " + actionHistory.size() + " 条记录");
        actionHistory.clear();
    }

    /**
     * 聚焦元素
     */
    private boolean focusOnElement(String selector) {
        AccessibilityNodeInfo node = findNodeBySelector(selector);
        if (node != null) {
            boolean success = node.performAction(AccessibilityNodeInfo.ACTION_FOCUS);
            Log.d(TAG, "聚焦元素 " + selector + ": " + (success ? "成功" : "失败"));
            node.recycle();
            return success;
        } else {
            Log.e(TAG, "未找到元素: " + selector);
            return false;
        }
    }

    /**
     * 检查动作是否正在执行
     */
    private boolean isActionInProgress(String actionId) {
        Long startTime = actionHistory.get(actionId);
        if (startTime == null) return false;

        // 检查动作是否已经超时(5秒)
        long elapsedTime = System.currentTimeMillis() - startTime;
        if (elapsedTime > 5000) {
            actionHistory.remove(actionId);
            return false;
        }

        return true;
    }

    /**
     * 记录动作开始执行
     */
    private void recordActionStart(String actionId) {
        actionHistory.put(actionId, System.currentTimeMillis());
    }

    /**
     * 记录动作完成
     */
    private void recordActionComplete(String actionId) {
        actionHistory.remove(actionId);
    }

    /**
     * 输入文本通过选择器
     */
    private boolean inputTextBySelector(String selector, String text) {
        AccessibilityNodeInfo node = findNodeBySelector(selector);
        if (node != null) {
            Bundle arguments = new Bundle();
            arguments.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
            boolean success = node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments);
            Log.d(TAG, "输入文本 '" + text + "' 到选择器 " + selector + ": " + (success ? "成功" : "失败"));
            node.recycle();
            return success;
        } else {
            Log.e(TAG, "未找到输入节点: " + selector);
            return false;
        }
    }

    /**
     * 获取UI状态并发送
     */
    /**
     * 获取UI状态并发送
     */
    private String getAndSendUIState() {
        String result = "";
        AccessibilityNodeInfo rootNode = getRootInActiveWindow();
        if (rootNode == null) {
            Log.e(TAG, "获取UI状态失败：无法获取窗口");
            notifyActionResult("get_ui_state", false, "无法获取窗口");
            return result;
        }

        try {
            // 构建符合MCP协议的DeviceState结构
            Map<String, Object> deviceState = new HashMap<>();
            deviceState.put("current_package", currentPackage);
            deviceState.put("current_activity", currentActivity);
            deviceState.put("screen_state", isScreenOn() ? "on" : "off"); // 添加屏幕状态

            // 添加UI层次结构
            deviceState.put("ui_hierarchy", buildNodeHierarchy(rootNode));

            // 提取可见文本
            deviceState.put("visible_text", extractVisibleTexts(rootNode));

            // 添加设备信息
            deviceState.put("device_info", getDeviceInfo());

            result = new JSONObject(deviceState).toString();
            notifyActionResult("get_ui_state", true, result);
        } catch (Exception e) {
            Log.e(TAG, "获取UI状态失败", e);
            notifyActionResult("get_ui_state", false, "获取UI状态失败: " + e.getMessage());
        } finally {
            rootNode.recycle();
        }
        return result;
    }

    /**
     * 检查屏幕是否打开
     */
    private boolean isScreenOn() {
        // 这里可以通过PowerManager来实现，但为简便起见，我们假设服务运行时屏幕总是开着的
        return true;
    }

    /**
     * 获取设备信息
     */
    private Map<String, String> getDeviceInfo() {
        Map<String, String> deviceInfo = new HashMap<>();
        deviceInfo.put("manufacturer", android.os.Build.MANUFACTURER);
        deviceInfo.put("model", android.os.Build.MODEL);
        deviceInfo.put("sdk", String.valueOf(android.os.Build.VERSION.SDK_INT));
        deviceInfo.put("release", android.os.Build.VERSION.RELEASE);

        // 获取屏幕宽高
        android.view.WindowManager wm = (android.view.WindowManager) getSystemService(Context.WINDOW_SERVICE);
        if (wm != null) {
            android.util.DisplayMetrics metrics = new android.util.DisplayMetrics();
            wm.getDefaultDisplay().getMetrics(metrics);
            deviceInfo.put("screen_width", String.valueOf(metrics.widthPixels));
            deviceInfo.put("screen_height", String.valueOf(metrics.heightPixels));
        }

        return deviceInfo;
    }

    /**
     * 构建节点层次结构 - 符合MCP协议要求
     */
    private Map<String, Object> buildNodeHierarchy(AccessibilityNodeInfo node) {
        if (node == null) return new HashMap<>();

        Map<String, Object> nodeInfo = new HashMap<>();

        // 基本属性
        CharSequence className = node.getClassName();
        CharSequence text = node.getText();
        CharSequence desc = node.getContentDescription();
        String id = node.getViewIdResourceName();

        if (className != null) nodeInfo.put("className", className.toString());
        if (text != null) nodeInfo.put("text", text.toString());
        if (desc != null) nodeInfo.put("contentDescription", desc.toString());
        if (id != null) nodeInfo.put("viewIdResourceName", id);

        // 状态属性
        nodeInfo.put("clickable", node.isClickable());
        nodeInfo.put("longClickable", node.isLongClickable());
        nodeInfo.put("focusable", node.isFocusable());
        nodeInfo.put("focused", node.isFocused());
        nodeInfo.put("selected", node.isSelected());
        nodeInfo.put("scrollable", node.isScrollable());
        nodeInfo.put("enabled", node.isEnabled());
        nodeInfo.put("password", node.isPassword());
        nodeInfo.put("checkable", node.isCheckable());
        nodeInfo.put("checked", node.isChecked());

        // 位置信息 - 按照MCP协议的格式
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        Map<String, Integer> boundsMap = new HashMap<>();
        boundsMap.put("left", bounds.left);
        boundsMap.put("top", bounds.top);
        boundsMap.put("right", bounds.right);
        boundsMap.put("bottom", bounds.bottom);
        nodeInfo.put("bounds", boundsMap);

        // 子节点
        List<Map<String, Object>> children = new ArrayList<>();
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                children.add(buildNodeHierarchy(child));
                child.recycle();
            }
        }
        nodeInfo.put("children", children);

        return nodeInfo;
    }

    /**
     * 获取已安装应用列表并发送
     */
    private String getAndSendInstalledApps() {
        try {
            PackageManager pm = getPackageManager();
            List<ApplicationInfo> installedApps = pm.getInstalledApplications(PackageManager.GET_META_DATA);

            List<Map<String, String>> appsList = new ArrayList<>();

            for (ApplicationInfo app : installedApps) {
                // 仅包含有启动意图的应用
                if (pm.getLaunchIntentForPackage(app.packageName) != null) {
                    Map<String, String> appInfo = new HashMap<>();
                    appInfo.put("packageName", app.packageName);
                    appInfo.put("appName", pm.getApplicationLabel(app).toString());
                    appsList.add(appInfo);
                }
            }

            return new JSONArray(appsList).toString();
        } catch (Exception e) {
            Log.e(TAG, "获取已安装应用列表失败", e);
        }
        return null;
    }

    /**
     * 查找元素并返回其信息
     */
    private void findAndReportElement(String selector) {
        AccessibilityNodeInfo node = findNodeBySelector(selector);

        Map<String, Object> elementInfo = new HashMap<>();

        if (node != null) {
            // 获取元素信息
            CharSequence text = node.getText();
            CharSequence desc = node.getContentDescription();
            String id = node.getViewIdResourceName();
            CharSequence className = node.getClassName();

            elementInfo.put("found", true);
            if (text != null) elementInfo.put("text", text.toString());
            if (desc != null) elementInfo.put("description", desc.toString());
            if (id != null) elementInfo.put("id", id);
            if (className != null) elementInfo.put("className", className.toString());

            // 获取边界
            Rect bounds = new Rect();
            node.getBoundsInScreen(bounds);
            Map<String, Integer> boundsMap = new HashMap<>();
            boundsMap.put("left", bounds.left);
            boundsMap.put("top", bounds.top);
            boundsMap.put("right", bounds.right);
            boundsMap.put("bottom", bounds.bottom);
            elementInfo.put("bounds", boundsMap);

            // 获取状态
            elementInfo.put("clickable", node.isClickable());
            elementInfo.put("longClickable", node.isLongClickable());
            elementInfo.put("focusable", node.isFocusable());
            elementInfo.put("focused", node.isFocused());
            elementInfo.put("selected", node.isSelected());
            elementInfo.put("scrollable", node.isScrollable());
            elementInfo.put("enabled", node.isEnabled());

            node.recycle();
        } else {
            elementInfo.put("found", false);
        }

        // 发送元素信息
        try {
            Intent intent = new Intent("com.jxev.ai.ELEMENT_INFO_RESPONSE");
            intent.putExtra("element_info_json", new JSONObject(elementInfo).toString());
            sendBroadcast(intent);

            notifyActionResult("find_element", true, "元素查找完成");
        } catch (Exception e) {
            Log.e(TAG, "发送元素信息失败", e);
            notifyActionResult("find_element", false, "发送元素信息失败: " + e.getMessage());
        }
    }

    /**
     * 启动应用
     */
    /**
     * 启动应用
     * @param packageNameOrComponent 可以是包名或完整组件名(包名/活动名)
     * @return 是否成功启动
     */
    private boolean launchApp(String packageNameOrComponent) {
        try {
            // 先检查输入是否为空
            if (TextUtils.isEmpty(packageNameOrComponent)) {
                Log.e(TAG, "无法启动应用: 包名或组件名为空");
                return false;
            }

            String packageName;
            String activityName = null;

            // 检查是否包含组件名（通过斜杠分隔）
            if (packageNameOrComponent.contains("/")) {
                String[] parts = packageNameOrComponent.split("/", 2);
                packageName = parts[0];
                activityName = parts[1];
                // 如果活动名称以点开头，需要将其与包名组合
                if (activityName.startsWith(".")) {
                    activityName = packageName + activityName;
                }
                Log.d(TAG, "解析组件名: 包名=" + packageName + ", 活动名=" + activityName);
            } else {
                packageName = packageNameOrComponent;
            }

            // 判断应用是否存在
            PackageManager pm = getPackageManager();
            try {
                ApplicationInfo appInfo = pm.getApplicationInfo(packageName, 0);
                if (!appInfo.enabled) {
                    Log.e(TAG, "应用已安装但被禁用: " + packageName);
                    return false;
                }
            } catch (PackageManager.NameNotFoundException e) {
                Log.e(TAG, "未找到应用: " + packageName);
                return false;
            }

            Intent launchIntent;

            // 如果指定了活动名称，直接使用组件名启动
            if (activityName != null) {
                launchIntent = new Intent();
                launchIntent.setComponent(new ComponentName(packageName, activityName));
                Log.d(TAG, "使用指定组件名启动: " + packageName + "/" + activityName);
            } else {
                // 否则使用默认启动Intent
                launchIntent = pm.getLaunchIntentForPackage(packageName);
                if (launchIntent == null) {
                    Log.e(TAG, "应用没有启动Intent: " + packageName);
                    return false;
                }
                Log.d(TAG, "使用默认Intent启动: " + packageName);
            }

            // 设置Intent标志
            launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK |
                    Intent.FLAG_ACTIVITY_CLEAR_TASK |
                    Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);

            // 确保有LAUNCHER类别（对于默认启动Intent）
            if (activityName == null) {
                launchIntent.addCategory(Intent.CATEGORY_LAUNCHER);
            }

            // 输出完整Intent信息，方便调试
            Log.d(TAG, "准备启动Intent: " + launchIntent.toUri(0));

            // 在主线程启动应用
            mainHandler.post(() -> {
                try {
                    getApplicationContext().startActivity(launchIntent);
                    Log.d(TAG, "成功在主线程启动应用");
                } catch (Exception e) {
                    Log.e(TAG, "在主线程启动应用失败", e);
                }
            });

            // 短暂延迟，让系统有时间处理
            try {
                Thread.sleep(300);
            } catch (InterruptedException e) {
                // 忽略中断异常
            }

            return true;
        } catch (Exception e) {
            Log.e(TAG, "启动应用时发生错误: " + packageNameOrComponent, e);
            return false;
        }
    }

    /**
     * 执行滑动操作
     */
    private void performSwipe(int x1, int y1, int x2, int y2, int duration) {
        Path path = new Path();
        path.moveTo(x1, y1);
        path.lineTo(x2, y2);

        GestureDescription.Builder builder = new GestureDescription.Builder();
        builder.addStroke(new GestureDescription.StrokeDescription(path, 0, duration));

        boolean success = dispatchGesture(builder.build(), new GestureResultCallback() {
            @Override
            public void onCompleted(GestureDescription gestureDescription) {
                super.onCompleted(gestureDescription);
                Log.d(TAG, "滑动完成: (" + x1 + "," + y1 + ") -> (" + x2 + "," + y2 + ")");
                notifyActionResult("swipe", true, "滑动完成");
            }

            @Override
            public void onCancelled(GestureDescription gestureDescription) {
                super.onCancelled(gestureDescription);
                Log.e(TAG, "滑动取消: (" + x1 + "," + y1 + ") -> (" + x2 + "," + y2 + ")");
                notifyActionResult("swipe", false, "滑动被取消");
            }
        }, null);

        Log.d(TAG, "滑动请求 (" + x1 + "," + y1 + ") -> (" + x2 + "," + y2 + "): " + (success ? "发送成功" : "发送失败"));
        if (!success) {
            notifyActionResult("swipe", false, "滑动请求发送失败");
        }
    }

    /**
     * 通过选择器点击节点
     */
    private boolean clickNodeBySelector(String selector) {
        AccessibilityNodeInfo node = findNodeBySelector(selector);
        if (node != null) {
            boolean success = node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            Log.d(TAG, "点击选择器" + selector + ":" + (success ? "成功" : "失败"));
            node.recycle();
            return success;
        } else {
            Log.e(TAG, "未找到选择器: " + selector);
            return false;
        }
    }

    /**
     * 通过选择器长按节点
     */
    private boolean longPressNodeBySelector(String selector) {
        AccessibilityNodeInfo node = findNodeBySelector(selector);
        if (node != null) {
            boolean success = node.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK);
            Log.d(TAG, "长按选择器" + selector + ":" + (success ? "成功" : "失败"));
            node.recycle();
            return success;
        } else {
            Log.e(TAG, "未找到选择器: " + selector);
            return false;
        }
    }

    /**
     * 通过选择器查找节点
     */
    private AccessibilityNodeInfo findNodeBySelector(String selector) {
        if (selector == null) return null;

        AccessibilityNodeInfo rootNode = getRootInActiveWindow();
        if (rootNode == null) return null;

        AccessibilityNodeInfo result = null;

        try {
            // 首先检查是否是简单格式的选择器
            if (selector.startsWith("id=")) {
                String id = selector.substring(3);
                result = findNodeById(rootNode, id);
            } else if (selector.startsWith("text=")) {
                String text = selector.substring(5);
                result = findNodeByText(rootNode, text);
            } else if (selector.startsWith("desc=")) {
                String desc = selector.substring(5);
                result = findNodeByContentDescription(rootNode, desc);
            } else if (selector.startsWith("class=")) {
                String className = selector.substring(6);
                result = findNodeByClassName(rootNode, className);
            } else {
                // 尝试作为JSON解析
                try {
                    JSONObject selectorObj = new JSONObject(selector);
                    Log.d(TAG, "解析JSON选择器: " + selectorObj.toString());

                    // 按优先级尝试不同属性
                    // 1. 首先尝试resourceId（最可靠）
                    if (selectorObj.has("resourceId") && !selectorObj.getString("resourceId").isEmpty()) {
                        String id = selectorObj.getString("resourceId");
                        result = findNodeById(rootNode, id);
                        Log.d(TAG, "通过resourceId尝试查找: " + id + ", 结果: " + (result != null));
                    }

                    // 2. 如果resourceId失败，尝试文本
                    if (result == null && selectorObj.has("text") && !selectorObj.getString("text").isEmpty()) {
                        String text = selectorObj.getString("text");
                        result = findNodeByText(rootNode, text);
                        Log.d(TAG, "通过text尝试查找: " + text + ", 结果: " + (result != null));
                    }

                    // 3. 然后尝试contentDescription
                    if (result == null && selectorObj.has("contentDescription") && !selectorObj.getString("contentDescription").isEmpty()) {
                        String desc = selectorObj.getString("contentDescription");
                        result = findNodeByContentDescription(rootNode, desc);
                        Log.d(TAG, "通过contentDescription尝试查找: " + desc + ", 结果: " + (result != null));
                    }

                    // 4. 最后尝试className（如果也提供了bounds可以增加精度）
                    if (result == null && selectorObj.has("className")) {
                        String className = selectorObj.getString("className");
                        // 如果有边界信息，尝试结合边界
                        if (selectorObj.has("bounds")) {
                            JSONObject bounds = selectorObj.getJSONObject("bounds");
                            // 确保边界框有效
                            if (bounds.has("left") && bounds.has("top") && bounds.has("right") && bounds.has("bottom")) {
                                int left = bounds.getInt("left");
                                int top = bounds.getInt("top");
                                int right = bounds.getInt("right");
                                int bottom = bounds.getInt("bottom");

                                // 确保边界框有效
                                if (right > left && bottom > top) {
                                    result = findNodeByClassNameAndBounds(rootNode, className, left, top, right, bottom);
                                    Log.d(TAG, "通过className和bounds尝试查找: " + className + ", 边界: [" + left + "," + top + "," + right + "," + bottom + "], 结果: " + (result != null));
                                }
                            }
                        }

                        // 如果边界查找失败或没有边界，仅使用className
                        if (result == null) {
                            result = findNodeByClassName(rootNode, className);
                            Log.d(TAG, "仅通过className尝试查找: " + className + ", 结果: " + (result != null));
                        }
                    }

                    // 5. 尝试直接使用边界框作为最后手段
                    if (result == null && selectorObj.has("bounds")) {
                        JSONObject bounds = selectorObj.getJSONObject("bounds");
                        if (bounds.has("left") && bounds.has("top") && bounds.has("right") && bounds.has("bottom")) {
                            int left = bounds.getInt("left");
                            int top = bounds.getInt("top");
                            int right = bounds.getInt("right");
                            int bottom = bounds.getInt("bottom");

                            // 确保边界框有效
                            if (right > left && bottom > top) {
                                result = findNodeByBounds(rootNode, left, top, right, bottom);
                                Log.d(TAG, "仅通过bounds尝试查找: [" + left + "," + top + "," + right + "," + bottom + "], 结果: " + (result != null));
                            }
                        }
                    }

                    // 6. 兼容服务端发送的旧格式选择器
                    if (result == null) {
                        // 旧选择器格式的备选尝试
                        if (selectorObj.has("id")) {
                            result = findNodeById(rootNode, selectorObj.getString("id"));
                        } else if (selectorObj.has("class")) {
                            result = findNodeByClassName(rootNode, selectorObj.getString("class"));
                        } else if (selectorObj.has("desc")) {
                            result = findNodeByContentDescription(rootNode, selectorObj.getString("desc"));
                        }
                    }
                } catch (JSONException e) {
                    // 不是JSON，尝试作为纯文本查找
                    Log.d(TAG, "非JSON选择器，尝试作为文本查找: " + selector);
                    result = findNodeByText(rootNode, selector);
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "解析选择器出错: " + e.getMessage(), e);
        }

        if (result == null) {
            Log.e(TAG, "未能通过选择器找到节点: " + selector);
        } else {
            Log.d(TAG, "成功找到节点: " + nodeToString(result));
        }

        rootNode.recycle();
        return result;
    }

    // 新增：通过类名和边界框查找节点
    private AccessibilityNodeInfo findNodeByClassNameAndBounds(AccessibilityNodeInfo root, String className, int left, int top, int right, int bottom) {
        if (root == null) return null;

        CharSequence nodeClassName = root.getClassName();
        if (nodeClassName != null && className.equals(nodeClassName.toString())) {
            // 检查边界是否匹配
            Rect bounds = new Rect();
            root.getBoundsInScreen(bounds);

            // 使用一个容差范围，因为有时候边界可能不是精确匹配的
            int tolerance = 10; // 10像素的容差
            boolean boundsMatch =
                    Math.abs(bounds.left - left) <= tolerance &&
                            Math.abs(bounds.top - top) <= tolerance &&
                            Math.abs(bounds.right - right) <= tolerance &&
                            Math.abs(bounds.bottom - bottom) <= tolerance;

            if (boundsMatch) {
                return AccessibilityNodeInfo.obtain(root);
            }
        }

        // 递归检查子节点
        for (int i = 0; i < root.getChildCount(); i++) {
            AccessibilityNodeInfo child = root.getChild(i);
            if (child != null) {
                AccessibilityNodeInfo result = findNodeByClassNameAndBounds(child, className, left, top, right, bottom);
                child.recycle();

                if (result != null) {
                    return result;
                }
            }
        }

        return null;
    }

    // 新增：仅通过边界框查找节点
    private AccessibilityNodeInfo findNodeByBounds(AccessibilityNodeInfo root, int left, int top, int right, int bottom) {
        if (root == null) return null;

        // 检查节点边界
        Rect bounds = new Rect();
        root.getBoundsInScreen(bounds);

        // 使用容差
        int tolerance = 10;
        boolean boundsMatch =
                Math.abs(bounds.left - left) <= tolerance &&
                        Math.abs(bounds.top - top) <= tolerance &&
                        Math.abs(bounds.right - right) <= tolerance &&
                        Math.abs(bounds.bottom - bottom) <= tolerance;

        if (boundsMatch) {
            return AccessibilityNodeInfo.obtain(root);
        }

        // 递归检查子节点
        for (int i = 0; i < root.getChildCount(); i++) {
            AccessibilityNodeInfo child = root.getChild(i);
            if (child != null) {
                AccessibilityNodeInfo result = findNodeByBounds(child, left, top, right, bottom);
                child.recycle();

                if (result != null) {
                    return result;
                }
            }
        }

        return null;
    }

    /**
     * 通过ID点击节点
     */
    private boolean clickNodeById(String viewId) {
        AccessibilityNodeInfo rootNode = getRootInActiveWindow();
        if (rootNode == null) {
            return false;
        }

        try {
            List<AccessibilityNodeInfo> nodes = rootNode.findAccessibilityNodeInfosByViewId(viewId);
            if (nodes != null && !nodes.isEmpty()) {
                AccessibilityNodeInfo node = nodes.get(0);
                boolean success = node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                Log.d(TAG, "点击节点ID " + viewId + ": " + (success ? "成功" : "失败"));
                node.recycle();
                return success;
            } else {
                Log.e(TAG, "未找到节点ID: " + viewId);
                return false;
            }
        } finally {
            rootNode.recycle();
        }
    }

    /**
     * 通过文本点击节点
     */
    private boolean clickNodeByText(String text) {
        AccessibilityNodeInfo rootNode = getRootInActiveWindow();
        if (rootNode == null) {
            return false;
        }

        try {
            List<AccessibilityNodeInfo> nodes = rootNode.findAccessibilityNodeInfosByText(text);
            if (nodes != null && !nodes.isEmpty()) {
                AccessibilityNodeInfo node = nodes.get(0);
                boolean success = node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                Log.d(TAG, "点击文本 " + text + ": " + (success ? "成功" : "失败"));
                node.recycle();
                return success;
            } else {
                Log.e(TAG, "未找到文本: " + text);
                return false;
            }
        } finally {
            rootNode.recycle();
        }
    }

    /**
     * 点击坐标位置
     */
    private void clickAtCoordinates(int x, int y) {
        Path path = new Path();
        path.moveTo(x, y);

        GestureDescription.Builder builder = new GestureDescription.Builder();
        builder.addStroke(new GestureDescription.StrokeDescription(path, 0, 50));

        boolean success = dispatchGesture(builder.build(), new GestureResultCallback() {
            @Override
            public void onCompleted(GestureDescription gestureDescription) {
                super.onCompleted(gestureDescription);
                Log.d(TAG, "坐标点击完成: (" + x + ", " + y + ")");
                notifyActionResult("click", true, "坐标点击完成");
            }

            @Override
            public void onCancelled(GestureDescription gestureDescription) {
                super.onCancelled(gestureDescription);
                Log.e(TAG, "坐标点击取消: (" + x + ", " + y + ")");
                notifyActionResult("click", false, "坐标点击取消");
            }
        }, null);

        Log.d(TAG, "点击坐标 (" + x + ", " + y + "): " + (success ? "发送成功" : "发送失败"));
        if (!success) {
            notifyActionResult("click", false, "坐标点击请求发送失败");
        }
    }

    /**
     * 输入文本到指定ID的节点
     */
    private boolean inputText(String viewId, String text) {
        AccessibilityNodeInfo rootNode = getRootInActiveWindow();
        if (rootNode == null) {
            return false;
        }

        try {
            List<AccessibilityNodeInfo> nodes = rootNode.findAccessibilityNodeInfosByViewId(viewId);
            if (nodes != null && !nodes.isEmpty()) {
                AccessibilityNodeInfo node = nodes.get(0);

                Bundle arguments = new Bundle();
                arguments.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
                boolean success = node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments);

                Log.d(TAG, "输入文本 '" + text + "' 到节点ID " + viewId + ": " + (success ? "成功" : "失败"));
                node.recycle();
                return success;
            } else {
                Log.e(TAG, "未找到输入节点ID: " + viewId);
                return false;
            }
        } finally {
            rootNode.recycle();
        }
    }

    /**
     * 执行滚动操作
     */
    private boolean performScroll(boolean isDown) {
        AccessibilityNodeInfo rootNode = getRootInActiveWindow();
        if (rootNode == null) {
            return false;
        }

        try {
            int action = isDown ? AccessibilityNodeInfo.ACTION_SCROLL_FORWARD :
                    AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD;

            boolean success = rootNode.performAction(action);
            if (success) {
                Log.d(TAG, "滚动 " + (isDown ? "向下" : "向上") + ": 成功");
                return true;
            } else {
                // 尝试在可滚动元素上执行
                boolean foundScrollable = findAndPerformScroll(rootNode, action);

                if (foundScrollable) {
                    Log.d(TAG, "在子元素上滚动 " + (isDown ? "向下" : "向上") + ": 成功");
                    return true;
                } else {
                    Log.e(TAG, "滚动失败: 未找到可滚动元素");
                    return false;
                }
            }
        } finally {
            rootNode.recycle();
        }
    }

    /**
     * 查找可滚动元素并执行滚动
     */
    private boolean findAndPerformScroll(AccessibilityNodeInfo node, int action) {
        if (node == null) return false;

        // 检查节点是否可滚动
        if (node.isScrollable()) {
            return node.performAction(action);
        }

        // 递归检查子节点
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                boolean result = findAndPerformScroll(child, action);
                child.recycle();

                if (result) {
                    return true;
                }
            }
        }

        return false;
    }

    /**
     * 通过ID执行长按操作
     */
    private boolean longPressNodeById(String viewId) {
        AccessibilityNodeInfo rootNode = getRootInActiveWindow();
        if (rootNode == null) {
            return false;
        }

        try {
            List<AccessibilityNodeInfo> nodes = rootNode.findAccessibilityNodeInfosByViewId(viewId);
            if (nodes != null && !nodes.isEmpty()) {
                AccessibilityNodeInfo node = nodes.get(0);
                boolean success = node.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK);
                Log.d(TAG, "长按节点ID " + viewId + ": " + (success ? "成功" : "失败"));
                node.recycle();
                return success;
            } else {
                Log.e(TAG, "未找到节点ID: " + viewId);
                return false;
            }
        } finally {
            rootNode.recycle();
        }
    }

    /**
     * 通过文本执行长按操作
     */
    private boolean longPressNodeByText(String text) {
        AccessibilityNodeInfo rootNode = getRootInActiveWindow();
        if (rootNode == null) {
            return false;
        }

        try {
            List<AccessibilityNodeInfo> nodes = rootNode.findAccessibilityNodeInfosByText(text);
            if (nodes != null && !nodes.isEmpty()) {
                AccessibilityNodeInfo node = nodes.get(0);
                boolean success = node.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK);
                Log.d(TAG, "长按文本 " + text + ": " + (success ? "成功" : "失败"));
                node.recycle();
                return success;
            } else {
                Log.e(TAG, "未找到文本: " + text);
                return false;
            }
        } finally {
            rootNode.recycle();
        }
    }

    /**
     * 在坐标位置执行长按操作
     */
    private void longPressAtCoordinates(int x, int y) {
        Path path = new Path();
        path.moveTo(x, y);

        GestureDescription.Builder builder = new GestureDescription.Builder();
        builder.addStroke(new GestureDescription.StrokeDescription(path, 0, 1000)); // 1秒长按

        boolean success = dispatchGesture(builder.build(), new GestureResultCallback() {
            @Override
            public void onCompleted(GestureDescription gestureDescription) {
                super.onCompleted(gestureDescription);
                Log.d(TAG, "长按坐标完成: (" + x + ", " + y + ")");
                notifyActionResult("long_press", true, "长按坐标完成");
            }

            @Override
            public void onCancelled(GestureDescription gestureDescription) {
                super.onCancelled(gestureDescription);
                Log.e(TAG, "长按坐标取消: (" + x + ", " + y + ")");
                notifyActionResult("long_press", false, "长按坐标取消");
            }
        }, null);

        Log.d(TAG, "长按坐标 (" + x + ", " + y + "): " + (success ? "发送成功" : "发送失败"));
        if (!success) {
            notifyActionResult("long_press", false, "长按坐标请求发送失败");
        }
    }

    // 辅助方法：通过ID查找节点
    private AccessibilityNodeInfo findNodeById(AccessibilityNodeInfo root, String id) {
        if (root == null) return null;

        List<AccessibilityNodeInfo> nodes = root.findAccessibilityNodeInfosByViewId(id);
        if (nodes != null && !nodes.isEmpty()) {
            return AccessibilityNodeInfo.obtain(nodes.get(0));
        }
        return null;
    }

    // 辅助方法：通过文本查找节点
    private AccessibilityNodeInfo findNodeByText(AccessibilityNodeInfo root, String text) {
        if (root == null) return null;

        List<AccessibilityNodeInfo> nodes = root.findAccessibilityNodeInfosByText(text);
        if (nodes != null && !nodes.isEmpty()) {
            return AccessibilityNodeInfo.obtain(nodes.get(0));
        }
        return null;
    }

    // 辅助方法：通过内容描述查找节点
    private AccessibilityNodeInfo findNodeByContentDescription(AccessibilityNodeInfo root, String desc) {
        if (root == null) return null;

        CharSequence rootDesc = root.getContentDescription();
        if (rootDesc != null && desc.equals(rootDesc.toString())) {
            return AccessibilityNodeInfo.obtain(root);
        }

        for (int i = 0; i < root.getChildCount(); i++) {
            AccessibilityNodeInfo child = root.getChild(i);
            if (child != null) {
                AccessibilityNodeInfo result = findNodeByContentDescription(child, desc);
                child.recycle();

                if (result != null) {
                    return result;
                }
            }
        }

        return null;
    }

    // 辅助方法：通过类名查找节点
    private AccessibilityNodeInfo findNodeByClassName(AccessibilityNodeInfo root, String className) {
        if (root == null) return null;

        CharSequence nodeClassName = root.getClassName();
        if (nodeClassName != null && className.equals(nodeClassName.toString())) {
            return AccessibilityNodeInfo.obtain(root);
        }

        for (int i = 0; i < root.getChildCount(); i++) {
            AccessibilityNodeInfo child = root.getChild(i);
            if (child != null) {
                AccessibilityNodeInfo result = findNodeByClassName(child, className);
                child.recycle();

                if (result != null) {
                    return result;
                }
            }
        }

        return null;
    }

    // 辅助方法：获取节点信息
    private Map<String, Object> getNodeInfo(AccessibilityNodeInfo node) {
        Map<String, Object> info = new HashMap<>();

        if (node == null) return info;

        // 获取基本属性
        CharSequence text = node.getText();
        CharSequence desc = node.getContentDescription();
        CharSequence className = node.getClassName();
        String id = node.getViewIdResourceName();

        if (text != null) info.put("text", text.toString());
        if (desc != null) info.put("description", desc.toString());
        if (className != null) info.put("className", className.toString());
        if (id != null) info.put("id", id);

        // 获取状态属性
        info.put("clickable", node.isClickable());
        info.put("longClickable", node.isLongClickable());
        info.put("checkable", node.isCheckable());
        info.put("checked", node.isChecked());
        info.put("enabled", node.isEnabled());
        info.put("focusable", node.isFocusable());
        info.put("focused", node.isFocused());
        info.put("scrollable", node.isScrollable());
        info.put("selected", node.isSelected());

        // 获取位置信息
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        Map<String, Integer> boundsMap = new HashMap<>();
        boundsMap.put("left", bounds.left);
        boundsMap.put("top", bounds.top);
        boundsMap.put("right", bounds.right);
        boundsMap.put("bottom", bounds.bottom);
        info.put("bounds", boundsMap);

        return info;
    }

    // 通知操作执行结果
    private void notifyActionResult(String actionType, boolean success, String message) {
        Intent intent = new Intent("com.jxev.ai.ACTION_RESULT");
        intent.putExtra("action_type", actionType);
        intent.putExtra("success", success);
        intent.putExtra("message", message);
        sendBroadcast(intent);
    }

    private boolean isAccessibilityServiceEnabled() {
        String serviceName = getPackageName() + "/" + MCPAccessibilityService.class.getCanonicalName();
        String enabledServices = Settings.Secure.getString(
                getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        return enabledServices != null && enabledServices.contains(serviceName);
    }
}