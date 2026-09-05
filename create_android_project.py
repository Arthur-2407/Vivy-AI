import os
import textwrap

PROJECT_DIR = os.path.join("d:\\", "Vivy", "android_node")

def write_file(path, content):
    full_path = os.path.join(PROJECT_DIR, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content).strip() + "\n")

def main():
    os.makedirs(PROJECT_DIR, exist_ok=True)
    print(f"Creating Android project in {PROJECT_DIR}")

    # Build scripts
    write_file("settings.gradle.kts", """
        pluginManagement {
            repositories {
                google()
                mavenCentral()
                gradlePluginPortal()
            }
        }
        dependencyResolutionManagement {
            repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
            repositories {
                google()
                mavenCentral()
            }
        }
        
        rootProject.name = "VivyNode"
        include(":app")
    """)

    write_file("build.gradle.kts", """
        buildscript {
            ext.kotlin_version = "1.9.0"
            repositories {
                google()
                mavenCentral()
            }
            dependencies {
                classpath("com.android.tools.build:gradle:8.1.2")
                classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:$kotlin_version")
            }
        }
    """)

    write_file("gradle.properties", """
        org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
        android.useAndroidX=true
        kotlin.code.style=official
    """)

    # App Module Build
    write_file("app/build.gradle.kts", """
        plugins {
            id("com.android.application")
            id("org.jetbrains.kotlin.android")
        }

        android {
            namespace = "com.vivy.node"
            compileSdk = 34

            defaultConfig {
                applicationId = "com.vivy.node"
                minSdk = 26
                targetSdk = 34
                versionCode = 1
                versionName = "1.0"
            }

            buildTypes {
                release {
                    isMinifyEnabled = true
                    proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
                }
            }
            compileOptions {
                sourceCompatibility = JavaVersion.VERSION_17
                targetCompatibility = JavaVersion.VERSION_17
            }
            kotlinOptions {
                jvmTarget = "17"
            }
            buildFeatures {
                compose = true
            }
            composeOptions {
                kotlinCompilerExtensionVersion = "1.5.1"
            }
        }

        dependencies {
            implementation("androidx.core:core-ktx:1.12.0")
            implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.6.2")
            implementation("androidx.activity:activity-compose:1.8.0")
            implementation(platform("androidx.compose:compose-bom:2023.08.00"))
            implementation("androidx.compose.ui:ui")
            implementation("androidx.compose.ui:ui-graphics")
            implementation("androidx.compose.ui:ui-tooling-preview")
            implementation("androidx.compose.material3:material3")
            
            // Security
            implementation("androidx.security:security-crypto:1.1.0-alpha06")
            
            // Networking
            implementation("com.squareup.okhttp3:okhttp:4.11.0")
            
            // CameraX
            val camerax_version = "1.3.0"
            implementation("androidx.camera:camera-core:${camerax_version}")
            implementation("androidx.camera:camera-camera2:${camerax_version}")
            implementation("androidx.camera:camera-lifecycle:${camerax_version}")
            implementation("androidx.camera:camera-view:${camerax_version}")
            
            // JSON
            implementation("org.json:json:20231013")
        }
    """)

    # Proguard
    write_file("app/proguard-rules.pro", """
        -keep class com.vivy.node.** { *; }
    """)

    # Manifest
    write_file("app/src/main/AndroidManifest.xml", """
        <?xml version="1.0" encoding="utf-8"?>
        <manifest xmlns:android="http://schemas.android.com/apk/res/android"
            package="com.vivy.node">

            <uses-feature android:name="android.hardware.camera" />
            <uses-permission android:name="android.permission.CAMERA" />
            <uses-permission android:name="android.permission.INTERNET" />
            <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
            <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />

            <application
                android:allowBackup="true"
                android:icon="@mipmap/ic_launcher"
                android:label="Vivy Node"
                android:roundIcon="@mipmap/ic_launcher_round"
                android:supportsRtl="true"
                android:theme="@style/Theme.VivyNode">
                <activity
                    android:name=".MainActivity"
                    android:exported="true"
                    android:configChanges="orientation|screenSize"
                    android:theme="@style/Theme.VivyNode">
                    <intent-filter>
                        <action android:name="android.intent.action.MAIN" />
                        <category android:name="android.intent.category.LAUNCHER" />
                    </intent-filter>
                </activity>
            </application>
        </manifest>
    """)

    # Resources (dummy styles/themes for now, let Compose handle UI)
    write_file("app/src/main/res/values/themes.xml", """
        <resources>
            <style name="Theme.VivyNode" parent="android:Theme.Material.Light.NoActionBar" />
        </resources>
    """)

    # Kotlin Code
    write_file("app/src/main/java/com/vivy/node/MainActivity.kt", """
        package com.vivy.node

        import android.Manifest
        import android.content.pm.PackageManager
        import android.os.Bundle
        import androidx.activity.ComponentActivity
        import androidx.activity.compose.setContent
        import androidx.activity.result.contract.ActivityResultContracts
        import androidx.compose.foundation.layout.*
        import androidx.compose.material3.*
        import androidx.compose.runtime.*
        import androidx.compose.ui.Modifier
        import androidx.compose.ui.unit.dp
        import androidx.core.content.ContextCompat
        import com.vivy.node.connection.HubConnectionManager
        import com.vivy.node.discovery.DiscoveryManager
        import com.vivy.node.camera.CameraCaptureManager
        import com.vivy.node.security.CredentialManager
        import com.vivy.node.ui.DashboardScreen

        class MainActivity : ComponentActivity() {

            private lateinit var connectionManager: HubConnectionManager
            private lateinit var discoveryManager: DiscoveryManager
            private lateinit var cameraCaptureManager: CameraCaptureManager
            private lateinit var credentialManager: CredentialManager

            private val requestPermissionLauncher = registerForActivityResult(
                ActivityResultContracts.RequestPermission()
            ) { isGranted: Boolean ->
                if (isGranted) {
                    startSystems()
                }
            }

            override fun onCreate(savedInstanceState: Bundle?) {
                super.onCreate(savedInstanceState)
                
                credentialManager = CredentialManager(this)
                connectionManager = HubConnectionManager(credentialManager)
                discoveryManager = DiscoveryManager(this) { host, port ->
                    connectionManager.connect(host, port)
                }
                cameraCaptureManager = CameraCaptureManager(this, connectionManager)

                setContent {
                    MaterialTheme {
                        Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                            DashboardScreen(connectionManager, discoveryManager, credentialManager, cameraCaptureManager)
                        }
                    }
                }

                if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                    startSystems()
                } else {
                    requestPermissionLauncher.launch(Manifest.permission.CAMERA)
                }
            }

            private fun startSystems() {
                discoveryManager.startDiscovery()
                cameraCaptureManager.startCamera()
            }

            override fun onDestroy() {
                super.onDestroy()
                discoveryManager.stopDiscovery()
                connectionManager.disconnect()
            }
        }
    """)

    write_file("app/src/main/java/com/vivy/node/security/CredentialManager.kt", """
        package com.vivy.node.security

        import android.content.Context
        import android.content.SharedPreferences
        import androidx.security.crypto.EncryptedSharedPreferences
        import androidx.security.crypto.MasterKey
        import java.util.UUID

        class CredentialManager(context: Context) {
            private val prefs: SharedPreferences

            init {
                val masterKey = MasterKey.Builder(context)
                    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                    .build()

                prefs = EncryptedSharedPreferences.create(
                    context,
                    "vivy_node_prefs",
                    masterKey,
                    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
                )
            }

            fun getDeviceId(): String {
                var id = prefs.getString("device_id", null)
                if (id == null) {
                    id = "vivy-android-" + UUID.randomUUID().toString().substring(0, 8)
                    prefs.edit().putString("device_id", id).apply()
                }
                return id
            }

            fun saveSessionKey(key: String) {
                prefs.edit().putString("session_key", key).apply()
            }

            fun getSessionKey(): String? {
                return prefs.getString("session_key", null)
            }

            fun clearSession() {
                prefs.edit().remove("session_key").apply()
            }
        }
    """)

    write_file("app/src/main/java/com/vivy/node/discovery/DiscoveryManager.kt", """
        package com.vivy.node.discovery

        import android.content.Context
        import android.net.nsd.NsdManager
        import android.net.nsd.NsdServiceInfo
        import android.util.Log

        class DiscoveryManager(context: Context, private val onHubFound: (String, Int) -> Unit) {
            private val nsdManager = context.getSystemService(Context.NSD_SERVICE) as NsdManager
            private val SERVICE_TYPE = "_vivy._tcp."
            
            private val discoveryListener = object : NsdManager.DiscoveryListener {
                override fun onDiscoveryStarted(regType: String) {
                    Log.d("Discovery", "Service discovery started")
                }
                
                override fun onServiceFound(service: NsdServiceInfo) {
                    Log.d("Discovery", "Service discovery success " + service)
                    if (service.serviceType == SERVICE_TYPE) {
                        nsdManager.resolveService(service, resolveListener)
                    }
                }
                
                override fun onServiceLost(service: NsdServiceInfo) {
                    Log.e("Discovery", "service lost: " + service)
                }
                
                override fun onDiscoveryStopped(serviceType: String) {
                    Log.i("Discovery", "Discovery stopped: " + serviceType)
                }
                
                override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                    Log.e("Discovery", "Discovery failed: Error code: " + errorCode)
                    nsdManager.stopServiceDiscovery(this)
                }
                
                override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
                    Log.e("Discovery", "Discovery failed: Error code: " + errorCode)
                    nsdManager.stopServiceDiscovery(this)
                }
            }
            
            private val resolveListener = object : NsdManager.ResolveListener {
                override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                    Log.e("Discovery", "Resolve failed: " + errorCode)
                }
                
                override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
                    Log.e("Discovery", "Resolve Succeeded. " + serviceInfo)
                    val host = serviceInfo.host.hostAddress
                    val port = serviceInfo.port
                    if (host != null) {
                        onHubFound(host, port)
                    }
                }
            }

            fun startDiscovery() {
                try {
                    nsdManager.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, discoveryListener)
                } catch (e: Exception) {
                    Log.e("Discovery", "Failed to start discovery", e)
                }
            }

            fun stopDiscovery() {
                try {
                    nsdManager.stopServiceDiscovery(discoveryListener)
                } catch (e: Exception) {
                    Log.e("Discovery", "Failed to stop discovery", e)
                }
            }
        }
    """)

    write_file("app/src/main/java/com/vivy/node/connection/HubConnectionManager.kt", """
        package com.vivy.node.connection

        import android.util.Log
        import com.vivy.node.security.CredentialManager
        import okhttp3.*
        import org.json.JSONObject
        import java.util.UUID
        import java.util.concurrent.TimeUnit
        import kotlinx.coroutines.flow.MutableStateFlow
        import kotlinx.coroutines.flow.StateFlow

        enum class ConnectionState {
            DISCONNECTED, CONNECTING, PAIRING_REQUIRED, CONNECTED
        }

        class HubConnectionManager(private val credentialManager: CredentialManager) {
            private val client = OkHttpClient.Builder()
                .readTimeout(0, TimeUnit.MILLISECONDS)
                .build()
            
            private var webSocket: WebSocket? = null
            
            private val _state = MutableStateFlow(ConnectionState.DISCONNECTED)
            val state: StateFlow<ConnectionState> = _state
            
            private val _pairingCode = MutableStateFlow<String?>(null)
            val pairingCode: StateFlow<String?> = _pairingCode

            private val _hubAddress = MutableStateFlow<String?>(null)
            val hubAddress: StateFlow<String?> = _hubAddress

            private val _latency = MutableStateFlow(0L)
            val latency: StateFlow<Long> = _latency
            
            private var requestTimes = mutableMapOf<String, Long>()

            fun connect(host: String, port: Int) {
                if (_state.value == ConnectionState.CONNECTED) return
                
                _hubAddress.value = "ws://\\$host:\\$port"
                _state.value = ConnectionState.CONNECTING
                
                val request = Request.Builder().url("ws://\\$host:\\$port").build()
                webSocket = client.newWebSocket(request, createListener())
            }

            fun disconnect() {
                webSocket?.close(1000, "Normal closure")
                _state.value = ConnectionState.DISCONNECTED
            }

            private fun createListener() = object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    Log.d("Connection", "WebSocket Opened")
                    val sessionKey = credentialManager.getSessionKey()
                    if (sessionKey != null) {
                        sendAuthenticateRequest(webSocket, sessionKey)
                    } else {
                        sendIdentityRequest(webSocket)
                    }
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    Log.d("Connection", "Received: \\$text")
                    try {
                        val json = JSONObject(text)
                        val type = json.optString("type")
                        
                        when (type) {
                            "pairing.challenge" -> {
                                _state.value = ConnectionState.PAIRING_REQUIRED
                                val payload = json.optJSONObject("payload")
                                _pairingCode.value = payload?.optString("pairing_code")
                            }
                            "identity.accept" -> {
                                val session = json.optString("session_id")
                                credentialManager.saveSessionKey(session)
                                _state.value = ConnectionState.CONNECTED
                                _pairingCode.value = null
                            }
                            "device.authenticate_ack" -> {
                                _state.value = ConnectionState.CONNECTED
                            }
                            "pairing.failed" -> {
                                credentialManager.clearSession()
                                _state.value = ConnectionState.DISCONNECTED
                            }
                            "capability.result" -> {
                                val reqId = json.optString("request_id")
                                requestTimes.remove(reqId)?.let { t0 ->
                                    _latency.value = System.currentTimeMillis() - t0
                                }
                            }
                        }
                    } catch (e: Exception) {
                        Log.e("Connection", "Message parse error", e)
                    }
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    Log.d("Connection", "Closed: \\$code \\$reason")
                    if (code == 1008) {
                        credentialManager.clearSession()
                    }
                    _state.value = ConnectionState.DISCONNECTED
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    Log.e("Connection", "Error", t)
                    _state.value = ConnectionState.DISCONNECTED
                }
            }

            private fun sendIdentityRequest(ws: WebSocket) {
                val req = JSONObject().apply {
                    put("protocol", "vivy")
                    put("version", "1")
                    put("message_id", UUID.randomUUID().toString())
                    put("type", "identity.request")
                    put("device_id", credentialManager.getDeviceId())
                    put("payload", JSONObject().apply {
                        put("device_type", "android")
                        put("hardware", org.json.JSONArray().apply {
                            put("camera")
                            put("mic")
                        })
                    })
                }
                ws.send(req.toString())
            }

            private fun sendAuthenticateRequest(ws: WebSocket, sessionKey: String) {
                val req = JSONObject().apply {
                    put("protocol", "vivy")
                    put("version", "1")
                    put("message_id", UUID.randomUUID().toString())
                    put("type", "device.authenticate")
                    put("device_id", credentialManager.getDeviceId())
                    put("security", JSONObject().apply {
                        put("session_key", sessionKey)
                    })
                }
                ws.send(req.toString())
            }

            fun sendPairingResponse(pin: String) {
                val ws = webSocket ?: return
                val req = JSONObject().apply {
                    put("protocol", "vivy")
                    put("version", "1")
                    put("message_id", UUID.randomUUID().toString())
                    put("type", "pairing.response")
                    put("device_id", credentialManager.getDeviceId())
                    put("payload", JSONObject().apply {
                        put("pin", pin)
                    })
                }
                ws.send(req.toString())
            }

            fun sendFrame(base64Image: String) {
                if (_state.value != ConnectionState.CONNECTED) return
                val sessionKey = credentialManager.getSessionKey() ?: return
                val ws = webSocket ?: return

                val reqId = UUID.randomUUID().toString()
                requestTimes[reqId] = System.currentTimeMillis()

                val req = JSONObject().apply {
                    put("protocol", "vivy")
                    put("version", "1")
                    put("message_id", reqId)
                    put("type", "capability.request")
                    put("device_id", credentialManager.getDeviceId())
                    put("session_id", sessionKey)
                    put("capability", "vision.gaze")
                    put("payload", JSONObject().apply {
                        put("image", base64Image)
                    })
                }
                ws.send(req.toString())
            }
        }
    """)

    write_file("app/src/main/java/com/vivy/node/camera/CameraCaptureManager.kt", """
        package com.vivy.node.camera

        import android.content.Context
        import android.graphics.Bitmap
        import android.graphics.BitmapFactory
        import android.graphics.ImageFormat
        import android.graphics.Matrix
        import android.graphics.Rect
        import android.graphics.YuvImage
        import android.util.Base64
        import androidx.camera.core.CameraSelector
        import androidx.camera.core.ImageAnalysis
        import androidx.camera.core.ImageProxy
        import androidx.camera.lifecycle.ProcessCameraProvider
        import androidx.core.content.ContextCompat
        import androidx.lifecycle.LifecycleOwner
        import com.vivy.node.connection.HubConnectionManager
        import java.io.ByteArrayOutputStream
        import java.util.concurrent.ExecutorService
        import java.util.concurrent.Executors

        class CameraCaptureManager(
            private val context: Context,
            private val connectionManager: HubConnectionManager
        ) {
            private var cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()
            private var lastFrameTime = 0L

            fun startCamera() {
                val cameraProviderFuture = ProcessCameraProvider.getInstance(context)

                cameraProviderFuture.addListener({
                    val cameraProvider: ProcessCameraProvider = cameraProviderFuture.get()

                    val imageAnalyzer = ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .build()
                        .also {
                            it.setAnalyzer(cameraExecutor) { image ->
                                processImage(image)
                            }
                        }

                    val cameraSelector = CameraSelector.DEFAULT_FRONT_CAMERA

                    try {
                        cameraProvider.unbindAll()
                        cameraProvider.bindToLifecycle(
                            context as LifecycleOwner, cameraSelector, imageAnalyzer
                        )
                    } catch (exc: Exception) {
                        exc.printStackTrace()
                    }

                }, ContextCompat.getMainExecutor(context))
            }

            private fun processImage(image: ImageProxy) {
                val currentTime = System.currentTimeMillis()
                // Target ~2 FPS => 500ms
                if (currentTime - lastFrameTime < 500) {
                    image.close()
                    return
                }
                lastFrameTime = currentTime

                val bitmap = imageProxyToBitmap(image)
                image.close()
                if (bitmap != null) {
                    // Resize to 640x480 max
                    val scaled = resizeAndMirror(bitmap)
                    val out = ByteArrayOutputStream()
                    scaled.compress(Bitmap.CompressFormat.JPEG, 70, out)
                    val base64 = Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
                    connectionManager.sendFrame(base64)
                }
            }

            private fun resizeAndMirror(bitmap: Bitmap): Bitmap {
                val width = bitmap.width
                val height = bitmap.height
                val scale = Math.min(640f / width, 480f / height)
                
                val matrix = Matrix()
                matrix.postScale(scale, scale)
                matrix.postScale(-1f, 1f, (width * scale) / 2f, (height * scale) / 2f)
                
                return Bitmap.createBitmap(bitmap, 0, 0, width, height, matrix, true)
            }

            private fun imageProxyToBitmap(image: ImageProxy): Bitmap? {
                if (image.format != ImageFormat.YUV_420_888) return null
                val yBuffer = image.planes[0].buffer
                val uBuffer = image.planes[1].buffer
                val vBuffer = image.planes[2].buffer

                val ySize = yBuffer.remaining()
                val uSize = uBuffer.remaining()
                val vSize = vBuffer.remaining()

                val nv21 = ByteArray(ySize + uSize + vSize)

                yBuffer.get(nv21, 0, ySize)
                vBuffer.get(nv21, ySize, vSize)
                uBuffer.get(nv21, ySize + vSize, uSize)

                val yuvImage = YuvImage(nv21, ImageFormat.NV21, image.width, image.height, null)
                val out = ByteArrayOutputStream()
                yuvImage.compressToJpeg(Rect(0, 0, yuvImage.width, yuvImage.height), 100, out)
                val imageBytes = out.toByteArray()
                return BitmapFactory.decodeByteArray(imageBytes, 0, imageBytes.size)
            }
        }
    """)

    write_file("app/src/main/java/com/vivy/node/ui/DashboardScreen.kt", """
        package com.vivy.node.ui

        import androidx.compose.foundation.layout.*
        import androidx.compose.material3.*
        import androidx.compose.runtime.*
        import androidx.compose.ui.Alignment
        import androidx.compose.ui.Modifier
        import androidx.compose.ui.unit.dp
        import com.vivy.node.connection.ConnectionState
        import com.vivy.node.connection.HubConnectionManager
        import com.vivy.node.discovery.DiscoveryManager
        import com.vivy.node.security.CredentialManager
        import com.vivy.node.camera.CameraCaptureManager

        @Composable
        fun DashboardScreen(
            connectionManager: HubConnectionManager,
            discoveryManager: DiscoveryManager,
            credentialManager: CredentialManager,
            cameraCaptureManager: CameraCaptureManager
        ) {
            val state by connectionManager.state.collectAsState()
            val pairingCode by connectionManager.pairingCode.collectAsState()
            val hubAddress by connectionManager.hubAddress.collectAsState()
            val latency by connectionManager.latency.collectAsState()

            var pinInput by remember { mutableStateOf("") }

            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(16.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(text = "VIVY NODE", style = MaterialTheme.typography.headlineMedium)
                Spacer(modifier = Modifier.height(24.dp))
                
                Text(text = "Status: \\$state")
                Text(text = "Device ID: \\${credentialManager.getDeviceId()}")
                
                Spacer(modifier = Modifier.height(16.dp))

                if (hubAddress != null) {
                    Text(text = "Hub: \\$hubAddress")
                }

                if (state == ConnectionState.CONNECTED) {
                    Text(text = "Latency: \\$latency ms")
                    Spacer(modifier = Modifier.height(16.dp))
                    Button(onClick = { connectionManager.disconnect() }) {
                        Text("Disconnect")
                    }
                } else if (state == ConnectionState.PAIRING_REQUIRED) {
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(text = "Enter Vivy PIN (shown on PC):")
                    if (pairingCode != null) {
                        Text(text = "(Debug PIN: \\$pairingCode)")
                    }
                    OutlinedTextField(
                        value = pinInput,
                        onValueChange = { pinInput = it },
                        label = { Text("PIN") }
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Button(onClick = { 
                        connectionManager.sendPairingResponse(pinInput)
                        pinInput = ""
                    }) {
                        Text("Connect")
                    }
                } else if (state == ConnectionState.DISCONNECTED) {
                    Spacer(modifier = Modifier.height(16.dp))
                    Button(onClick = { discoveryManager.startDiscovery() }) {
                        Text("Discover Hub")
                    }
                }
            }
        }
    """)

    print("Android project successfully created!")

if __name__ == "__main__":
    main()
