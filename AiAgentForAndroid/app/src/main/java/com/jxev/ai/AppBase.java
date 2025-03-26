package com.jxev.ai;

import android.app.Application;
import android.util.Log;

public class AppBase extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        Log.d("Jerry","AppBase onCreate Success");
    }
}
