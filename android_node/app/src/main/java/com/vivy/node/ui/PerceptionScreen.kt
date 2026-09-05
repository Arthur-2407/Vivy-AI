package com.vivy.node.ui

import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.vivy.node.camera.CameraCaptureManager
import com.vivy.node.connection.HubConnectionManager

@Composable
fun PerceptionScreen(
    connectionManager: HubConnectionManager,
    cameraCaptureManager: CameraCaptureManager
) {
    val perceptionResult by connectionManager.perceptionResult.collectAsState()
    var isStreaming by remember { mutableStateOf(false) }
    
    DisposableEffect(Unit) {
        onDispose {
            if (isStreaming) {
                cameraCaptureManager.stopCamera()
                isStreaming = false
            }
        }
    }
    
    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Multimodal Perception", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(16.dp))
        
        Card(
            modifier = Modifier.fillMaxWidth().height(300.dp),
            colors = CardDefaults.cardColors(containerColor = Color.Black)
        ) {
            Box(modifier = Modifier.fillMaxSize()) {
                if (isStreaming) {
                    AndroidView(
                        factory = { ctx ->
                            val previewView = PreviewView(ctx)
                            cameraCaptureManager.startCamera(previewView.surfaceProvider)
                            previewView
                        },
                        modifier = Modifier.fillMaxSize()
                    )
                } else {
                    Text(
                        "Camera Stream Paused",
                        color = Color.Gray,
                        modifier = Modifier.align(Alignment.Center)
                    )
                }
            }
        }
        
        Spacer(Modifier.height(16.dp))
        
        Button(
            onClick = {
                if (isStreaming) {
                    cameraCaptureManager.stopCamera()
                    isStreaming = false
                } else {
                    isStreaming = true
                }
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(if (isStreaming) "Stop Streaming" else "Start Streaming")
        }
        
        Spacer(Modifier.height(16.dp))
        
        Text("Hub Vision Inference Stream", style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(8.dp))
        
        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .background(Color(0xFF1E1E1E))
                .padding(12.dp)
        ) {
            val resultText = perceptionResult ?: "Waiting for inference payload..."
            Text(
                text = resultText,
                color = Color.Green,
                modifier = Modifier.verticalScroll(rememberScrollState())
            )
        }
    }
}
