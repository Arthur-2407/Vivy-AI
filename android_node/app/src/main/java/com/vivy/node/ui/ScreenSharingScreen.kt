package com.vivy.node.ui

import android.graphics.BitmapFactory
import android.util.Base64
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import android.util.Log
import com.vivy.node.connection.HubConnectionManager
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject

private val Purple = Color(0xFF7C3AED)
private val Pink = Color(0xFFEC4899)
private val Dark = Color(0xFF0D0D1A)
private val Card = Color(0xFF13132A)

// State enum for screen share
private enum class ShareState { IDLE, CONNECTING, STREAMING, ERROR }

@Composable
fun ScreenSharingScreen(connectionManager: HubConnectionManager) {
    var shareState by remember { mutableStateOf(ShareState.IDLE) }
    var statusMessage by remember { mutableStateOf("Ready to connect to host screen.") }
    var errorMessage by remember { mutableStateOf("") }
    
    var currentFrameBitmap by remember { mutableStateOf<ImageBitmap?>(null) }
    var frameCounter by remember { mutableStateOf(0) }
    var decodedFrames by remember { mutableStateOf(0) }
    var renderedFrames by remember { mutableStateOf(0) }
    
    val scope = rememberCoroutineScope()

    // Polling loop: while STREAMING, refresh screenshot every 2 seconds
    LaunchedEffect(shareState) {
        if (shareState == ShareState.STREAMING) {
            while (shareState == ShareState.STREAMING) {
                try {
                    val req = JSONObject().apply { put("action", "capture") }
                    val response = connectionManager.requestCapability("vision.screen_capture", req)
                    val errorField = response.optString("error", "")
                    if (errorField.isNotEmpty()) {
                        statusMessage = "Stream error: $errorField"
                        shareState = ShareState.ERROR
                        errorMessage = errorField
                        break
                    }
                    
                    if (response.optBoolean("success", false)) {
                        // The host screenshot is ready. Fetch the actual frame bytes via the Hub!
                        val frameResponse = connectionManager.requestCapability("screen.frame", JSONObject())
                        val b64 = frameResponse.optString("frame_b64", "")
                        
                        if (b64.isNotEmpty()) {
                            try {
                                val decodedBytes = Base64.decode(b64, Base64.NO_WRAP)
                                val bitmap = BitmapFactory.decodeByteArray(decodedBytes, 0, decodedBytes.size)
                                decodedFrames++
                                if (bitmap != null) {
                                    currentFrameBitmap = bitmap.asImageBitmap()
                                    renderedFrames++
                                    frameCounter++
                                    statusMessage = "Streaming host screen • frame #$frameCounter"
                                } else {
                                    Log.e("ScreenShare", "decodeByteArray returned null for ${decodedBytes.size} bytes")
                                }
                            } catch (e: Exception) {
                                Log.e("ScreenShare", "Base64 decode error: ${e.message}")
                            }
                        } else {
                            statusMessage = "Connected — waiting for frame data…"
                        }
                    }
                } catch (e: Exception) {
                    errorMessage = e.message ?: "Stream interrupted"
                    shareState = ShareState.ERROR
                    break
                }
                delay(2000L) // Poll every 2 seconds
            }
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().background(Dark).padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            "Screen Sharing",
            fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Pink,
            modifier = Modifier.align(Alignment.Start)
        )
        Text(
            "View the primary host's screen remotely",
            fontSize = 12.sp, color = Color(0xFF64748B),
            modifier = Modifier.align(Alignment.Start).padding(bottom = 16.dp)
        )

        Card(
            colors = CardDefaults.cardColors(containerColor = Card),
            modifier = Modifier.fillMaxWidth().weight(1f).padding(bottom = 16.dp)
        ) {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                when (shareState) {
                    ShareState.STREAMING -> {
                        if (currentFrameBitmap != null) {
                            Image(
                                bitmap = currentFrameBitmap!!,
                                contentDescription = "Host screen",
                                contentScale = ContentScale.Fit,
                                modifier = Modifier.fillMaxSize().clip(RoundedCornerShape(8.dp))
                            )
                            // Overlay status badge
                            Box(
                                modifier = Modifier
                                    .align(Alignment.TopEnd)
                                    .padding(8.dp)
                                    .background(Color(0xCC000000), RoundedCornerShape(4.dp))
                                    .padding(horizontal = 8.dp, vertical = 4.dp)
                            ) {
                                Text(
                                    "● LIVE",
                                    color = Color(0xFF22C55E), fontSize = 10.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        } else {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                CircularProgressIndicator(color = Purple, modifier = Modifier.size(32.dp))
                                Spacer(Modifier.height(12.dp))
                                Text("Connecting to host screen…", color = Color.White, fontSize = 13.sp)
                            }
                        }
                    }
                    ShareState.CONNECTING -> {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            CircularProgressIndicator(color = Purple, modifier = Modifier.size(32.dp))
                            Spacer(Modifier.height(12.dp))
                            Text("Requesting screen capture from Hub…",
                                color = Color.White, fontSize = 13.sp, textAlign = TextAlign.Center)
                        }
                    }
                    ShareState.ERROR -> {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            modifier = Modifier.padding(24.dp)
                        ) {
                            Icon(Icons.Filled.Share, contentDescription = null,
                                tint = Color(0xFFEF4444), modifier = Modifier.size(48.dp))
                            Spacer(Modifier.height(16.dp))
                            Text(
                                errorMessage.ifEmpty { "Screen capture failed." },
                                color = Color(0xFFEF4444), fontSize = 13.sp,
                                textAlign = TextAlign.Center
                            )
                        }
                    }
                    ShareState.IDLE -> {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(Icons.Filled.Share, contentDescription = null,
                                tint = Purple, modifier = Modifier.size(48.dp))
                            Spacer(Modifier.height(16.dp))
                            Text(statusMessage, color = Color.White, fontSize = 14.sp,
                                textAlign = TextAlign.Center)
                        }
                    }
                }
            }
        }

        // Status label under the frame area
        if (shareState == ShareState.STREAMING && currentFrameBitmap != null) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(statusMessage, color = Color(0xFF94A3B8), fontSize = 11.sp,
                    modifier = Modifier.padding(bottom = 8.dp))
                Column(horizontalAlignment = Alignment.End) {
                    Text("Decoded: $decodedFrames", color = Color(0xFF64748B), fontSize = 10.sp)
                    Text("Rendered: $renderedFrames", color = Color(0xFF64748B), fontSize = 10.sp)
                }
            }
        }

        // Control button
        Button(
            onClick = {
                when (shareState) {
                    ShareState.IDLE, ShareState.ERROR -> {
                        scope.launch {
                            errorMessage = ""
                            currentFrameBitmap = null
                            frameCounter = 0
                            shareState = ShareState.CONNECTING
                            try {
                                val req = JSONObject().apply { put("action", "start") }
                                val response = connectionManager.requestCapability("vision.screen_capture", req)
                                val errorField = response.optString("error", "")
                                if (errorField.isNotEmpty()) {
                                    errorMessage = errorField
                                    shareState = ShareState.ERROR
                                } else {
                                    shareState = ShareState.STREAMING
                                }
                            } catch (e: Exception) {
                                errorMessage = e.message ?: "Failed to start screen stream."
                                shareState = ShareState.ERROR
                            }
                        }
                    }
                    ShareState.STREAMING, ShareState.CONNECTING -> {
                        shareState = ShareState.IDLE
                        currentFrameBitmap = null
                        statusMessage = "Screen sharing stopped."
                        frameCounter = 0
                    }
                }
            },
            colors = ButtonDefaults.buttonColors(
                containerColor = when (shareState) {
                    ShareState.STREAMING, ShareState.CONNECTING -> Color(0xFFEF4444)
                    else -> Purple
                }
            ),
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(
                when (shareState) {
                    ShareState.STREAMING -> "Stop Stream"
                    ShareState.CONNECTING -> "Stop"
                    ShareState.ERROR -> "Retry"
                    ShareState.IDLE -> "Start Stream"
                },
                color = Color.White
            )
        }
    }
}
