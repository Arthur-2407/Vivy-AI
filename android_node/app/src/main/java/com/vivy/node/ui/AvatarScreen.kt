package com.vivy.node.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.foundation.Image
import android.graphics.BitmapFactory
import android.util.Base64
import android.util.Log
import com.vivy.node.connection.HubConnectionManager
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject

private val Purple = Color(0xFF7C3AED)
private val Pink = Color(0xFFEC4899)
private val Dark = Color(0xFF0D0D1A)
private val Card = Color(0xFF13132A)

@Composable
fun AvatarScreen(connectionManager: HubConnectionManager) {
    // Avatar state from canonical backend
    var avatarStatus by remember { mutableStateOf("—") }   // STANDBY | STREAMING | OFFLINE
    var clientCount by remember { mutableStateOf(0) }
    var measuredFps by remember { mutableStateOf(0.0) }
    var rootCause by remember { mutableStateOf("") }
    var isConnected by remember { mutableStateOf(false) }
    var isDisabled by remember { mutableStateOf(false) }
    var isLoading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    // Show avatar frame image when MateEngine is streaming
    var showFrame by remember { mutableStateOf(false) }
    var currentFrameBitmap by remember { mutableStateOf<ImageBitmap?>(null) }
    val scope = rememberCoroutineScope()

    val hubUrl by connectionManager.hubAddress.collectAsState()
    val hostIp = hubUrl?.removePrefix("ws://")?.substringBefore(":") ?: ""

    // Status indicator color
    val statusColor by animateColorAsState(
        targetValue = when {
            isDisabled -> Color(0xFF64748B)
            isConnected -> Color(0xFF22C55E)
            error.isNotEmpty() -> Color(0xFFEF4444)
            else -> Color(0xFFEAB308)
        },
        animationSpec = tween(300), label = "status_color"
    )

    // Poll avatar status every 5 seconds
    LaunchedEffect(Unit) {
        while (true) {
            try {
                val response = connectionManager.requestCapability("avatar.status", JSONObject())
                val errField = response.optString("error", "")
                if (errField.isNotEmpty()) {
                    error = errField
                } else {
                    error = ""
                    avatarStatus = response.optString("status", "STANDBY")
                    clientCount = response.optInt("client_count", 0)
                    measuredFps = response.optDouble("measured_fps", 0.0)
                    rootCause = response.optString("root_cause", "")
                    isConnected = response.optBoolean("connected", false)
                    isDisabled = response.optBoolean("disabled", false)
                    // If MateEngine is streaming frames, offer to show the avatar frame
                    if (avatarStatus == "STREAMING") {
                        showFrame = true
                    }
                }
            } catch (e: Exception) {
                error = e.message ?: "Cannot reach avatar.status capability"
            }
            delay(5000L)
        }
    }

    var decodedFrames by remember { mutableStateOf(0) }
    var renderedFrames by remember { mutableStateOf(0) }

    // Stream frames when streaming
    LaunchedEffect(showFrame) {
        if (showFrame) {
            while (true) {
                try {
                    val frameResponse = connectionManager.requestCapability("avatar.frame", JSONObject())
                    val b64 = frameResponse.optString("frame_b64", "")
                    if (b64.isNotEmpty()) {
                        try {
                            val decodedBytes = Base64.decode(b64, Base64.NO_WRAP)
                            val bitmap = BitmapFactory.decodeByteArray(decodedBytes, 0, decodedBytes.size)
                            decodedFrames++
                            if (bitmap != null) {
                                currentFrameBitmap = bitmap.asImageBitmap()
                                renderedFrames++
                            } else {
                                Log.e("AvatarScreen", "decodeByteArray returned null for ${decodedBytes.size} bytes")
                            }
                        } catch (e: Exception) {
                            Log.e("AvatarScreen", "Base64 decode error: ${e.message}")
                        }
                    }
                } catch (e: Exception) {
                    Log.e("AvatarScreen", "Frame fetch error: ${e.message}")
                }
                delay(100L) // roughly 10 fps max for battery
            }
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().background(Dark).padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            "Avatar",
            fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Pink,
            modifier = Modifier.align(Alignment.Start)
        )
        Text(
            "MateEngine Unity renderer on the primary host",
            fontSize = 12.sp, color = Color(0xFF64748B),
            modifier = Modifier.align(Alignment.Start).padding(bottom = 16.dp)
        )

        // Status card
        Card(
            colors = CardDefaults.cardColors(containerColor = Card),
            modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    // Status dot
                    Box(
                        modifier = Modifier
                            .size(10.dp)
                            .background(statusColor, RoundedCornerShape(5.dp))
                    )
                    Spacer(Modifier.width(10.dp))
                    Text(
                        avatarStatus,
                        color = statusColor, fontSize = 14.sp, fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.weight(1f))
                    if (measuredFps > 0 || renderedFrames > 0) {
                        Column(horizontalAlignment = Alignment.End) {
                            if (measuredFps > 0) {
                                Text(
                                    "${String.format("%.1f", measuredFps)} FPS",
                                    color = Color(0xFF94A3B8), fontSize = 12.sp
                                )
                            }
                            Text(
                                "Decoded: $decodedFrames",
                                color = Color(0xFF64748B), fontSize = 10.sp
                            )
                            Text(
                                "Rendered: $renderedFrames",
                                color = Color(0xFF64748B), fontSize = 10.sp
                            )
                        }
                    }
                }

                if (rootCause.isNotEmpty()) {
                    Spacer(Modifier.height(10.dp))
                    Text(rootCause, color = Color(0xFF94A3B8), fontSize = 12.sp)
                }

                if (error.isNotEmpty()) {
                    Spacer(Modifier.height(10.dp))
                    Text(
                        "Hub error: $error",
                        color = Color(0xFFEF4444), fontSize = 12.sp
                    )
                }

                Spacer(Modifier.height(10.dp))
                Row {
                    InfoChip(label = "Unity Clients", value = clientCount.toString())
                    Spacer(Modifier.width(8.dp))
                    InfoChip(label = "Renderer", value = "MateEngine")
                }
            }
        }

        var emotion by remember { mutableStateOf("Relaxed") }
        var affection by remember { mutableStateOf(48) }
        var mode by remember { mutableStateOf("Companion Mode") }
        
        LaunchedEffect(Unit) {
            while (true) {
                try {
                    val cogResponse = connectionManager.requestCapability("cognition.state", JSONObject())
                    val emotionObj = cogResponse.optJSONObject("emotion")
                    if (emotionObj != null) {
                        emotion = emotionObj.optString("primary", "Relaxed")
                    }
                    val affectionObj = cogResponse.optJSONObject("affection")
                    if (affectionObj != null) {
                        affection = affectionObj.optInt("level", 48)
                    }
                    mode = cogResponse.optString("current_mode", "Companion Mode")
                } catch (e: Exception) {
                    // Ignore errors
                }
                delay(2000L)
            }
        }

        if (showFrame && currentFrameBitmap != null) {
            Card(
                colors = CardDefaults.cardColors(containerColor = Card),
                modifier = Modifier.fillMaxWidth().weight(1f).padding(bottom = 12.dp)
            ) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Image(
                        bitmap = currentFrameBitmap!!,
                        contentDescription = "Live avatar frame",
                        contentScale = ContentScale.Fit,
                        modifier = Modifier
                            .fillMaxSize()
                            .clip(RoundedCornerShape(8.dp))
                    )
                    // Overlays
                    Column(
                        modifier = Modifier
                            .align(Alignment.TopStart)
                            .padding(8.dp)
                    ) {
                        Box(modifier = Modifier.background(Color(0xCC000000), RoundedCornerShape(4.dp)).padding(6.dp)) {
                            Text("Emotion: $emotion", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        }
                        Spacer(Modifier.height(4.dp))
                        Box(modifier = Modifier.background(Color(0xCC000000), RoundedCornerShape(4.dp)).padding(6.dp)) {
                            Text("Affection: LVL $affection", color = Color(0xFFF43F5E), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        }
                        Spacer(Modifier.height(4.dp))
                        Box(modifier = Modifier.background(Color(0xCC000000), RoundedCornerShape(4.dp)).padding(6.dp)) {
                            Text(mode, color = Color(0xFF3B82F6), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                    
                    // "LIVE" badge
                    Box(
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .padding(8.dp)
                            .background(Color(0xCC000000), RoundedCornerShape(4.dp))
                            .padding(horizontal = 8.dp, vertical = 4.dp)
                    ) {
                        Text("● LIVE", color = Color(0xFF22C55E), fontSize = 10.sp,
                            fontWeight = FontWeight.Bold)
                    }
                }
            }
        } else if (!showFrame) {
            // Placeholder when not streaming
            Card(
                colors = CardDefaults.cardColors(containerColor = Card),
                modifier = Modifier.fillMaxWidth().weight(1f).padding(bottom = 12.dp)
            ) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            Icons.Filled.Person,
                            contentDescription = null,
                            tint = Purple.copy(alpha = 0.4f),
                            modifier = Modifier.size(72.dp)
                        )
                        Spacer(Modifier.height(12.dp))
                        Text(
                            if (isDisabled) "Avatar subsystem disabled"
                            else "MateEngine not streaming.\nStart Vivy on the primary host.",
                            color = Color(0xFF64748B), fontSize = 13.sp,
                            textAlign = TextAlign.Center
                        )
                    }
                }
            }
        }

        // Refresh button
        Button(
            onClick = {
                scope.launch {
                    isLoading = true
                    try {
                        val response = connectionManager.requestCapability("avatar.status", JSONObject())
                        val errField = response.optString("error", "")
                        if (errField.isNotEmpty()) {
                            error = errField
                        } else {
                            error = ""
                            avatarStatus = response.optString("status", "STANDBY")
                            clientCount = response.optInt("client_count", 0)
                            measuredFps = response.optDouble("measured_fps", 0.0)
                            rootCause = response.optString("root_cause", "")
                            isConnected = response.optBoolean("connected", false)
                            isDisabled = response.optBoolean("disabled", false)
                            if (avatarStatus == "STREAMING") {
                                showFrame = true
                            }
                        }
                    } catch (e: Exception) {
                        error = e.message ?: "Refresh failed"
                    } finally {
                        isLoading = false
                    }
                }
            },
            colors = ButtonDefaults.buttonColors(containerColor = Purple),
            modifier = Modifier.fillMaxWidth()
        ) {
            if (isLoading) {
                CircularProgressIndicator(color = Color.White, modifier = Modifier.size(16.dp),
                    strokeWidth = 2.dp)
                Spacer(Modifier.width(8.dp))
            } else {
                Icon(Icons.Filled.Refresh, contentDescription = null,
                    tint = Color.White, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(8.dp))
            }
            Text("Refresh Avatar State", color = Color.White)
        }
    }
}

@Composable
private fun InfoChip(label: String, value: String) {
    Box(
        modifier = Modifier
            .background(Color(0xFF1E1E3A), RoundedCornerShape(6.dp))
            .padding(horizontal = 10.dp, vertical = 5.dp)
    ) {
        Text("$label: $value", color = Color(0xFF94A3B8), fontSize = 11.sp)
    }
}
