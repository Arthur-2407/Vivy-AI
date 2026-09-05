package com.vivy.node.ui

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.MediaPlayer
import android.util.Base64
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vivy.node.connection.HubConnectionManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.io.File

data class VoiceIdentity(val id: String, val name: String, val language: String?, val active: Boolean?)

private val Purple = Color(0xFF7C3AED)
private val Pink = Color(0xFFEC4899)
private val Dark = Color(0xFF0D0D1A)
private val Card = Color(0xFF13132A)
private val Border = Color(0xFF2A2A4A)

@Composable
fun VoiceScreen(connectionManager: HubConnectionManager) {
    val scope = rememberCoroutineScope()
    var identities by remember { mutableStateOf<List<VoiceIdentity>>(emptyList()) }
    var switchMessage by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf("") }
    val context = LocalContext.current
    var isRecording by remember { mutableStateOf(false) }

    fun loadProfiles() {
        scope.launch {
            try {
                isLoading = true
                val response = connectionManager.requestCapability("voice.profiles", JSONObject())
                val status = response.optString("status")
                if (status == "error") {
                    val payload = response.optJSONObject("payload")
                    error = payload?.optString("error") ?: "Hub denied access to voice profiles."
                } else {
                    val activeVoiceId = response.optString("active_voice_id", "")
                    val profilesArray = response.optJSONArray("profiles")
                    val parsedIdentities = mutableListOf<VoiceIdentity>()
                    if (profilesArray != null) {
                        for (i in 0 until profilesArray.length()) {
                            val obj = profilesArray.optJSONObject(i) ?: continue
                            val voiceId = obj.optString("voice_id")
                            val langArray = obj.optJSONArray("language_support")
                            val lang = langArray?.optString(0) ?: obj.optString("language", "en")
                            parsedIdentities.add(
                                VoiceIdentity(
                                    id = voiceId,
                                    name = obj.optString("name"),
                                    active = voiceId == activeVoiceId,
                                    language = lang
                                )
                            )
                        }
                    }
                    identities = parsedIdentities
                }
            } catch (e: Exception) {
                error = e.message ?: "Failed to load voice identities via Hub"
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(Unit) {
        loadProfiles()
    }

    Column(
        modifier = Modifier.fillMaxSize().background(Dark).padding(16.dp)
    ) {
        Text(
            "Voice Identity",
            fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Pink
        )
        Text(
            "Powered by RVC neural training on the primary host",
            fontSize = 12.sp, color = Color(0xFF64748B), modifier = Modifier.padding(bottom = 16.dp)
        )

        if (switchMessage.isNotEmpty()) {
            Text(switchMessage, color = Color(0xFF22C55E), fontSize = 13.sp,
                modifier = Modifier.padding(bottom = 8.dp))
        }

        if (error.isNotEmpty()) {
            Text(error, color = Color(0xFFEF4444), fontSize = 13.sp,
                modifier = Modifier.padding(bottom = 8.dp))
        }

        if (isLoading) {
            CircularProgressIndicator(color = Purple, modifier = Modifier.align(Alignment.CenterHorizontally))
        } else {
            Text("Voice Profiles", color = Color(0xFF94A3B8), fontSize = 12.sp,
                modifier = Modifier.padding(bottom = 8.dp))
            LazyColumn(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(identities) { voice ->
                    VoiceIdentityCard(
                        voice = voice,
                        onSwitch = {
                            scope.launch {
                                try {
                                    val req = JSONObject().apply {
                                        put("identity_id", voice.id)
                                    }
                                    val response = connectionManager.requestCapability("voice.switch", req)
                                    val err = response.optString("error", "")
                                    switchMessage = if (err.isNotEmpty()) {
                                        "Switch failed: $err"
                                    } else {
                                        loadProfiles()
                                        "✓ Switched to ${voice.name}"
                                    }
                                } catch (e: Exception) {
                                    switchMessage = "Switch error: ${e.message}"
                                }
                            }
                        },
                        onPreview = {
                            scope.launch {
                                try {
                                    switchMessage = "Generating preview..."
                                    val req = JSONObject().apply { 
                                        put("voice_id", voice.id)
                                        put("prompt", "Hello, I am ${voice.name}.")
                                    }
                                    val res1 = connectionManager.requestCapability("voice.preview_generate", req)
                                    val url = res1.optString("preview_url", "")
                                    
                                    if (url.isNotEmpty()) {
                                        val fileParam = url.substringAfter("file=")
                                        val req2 = JSONObject().apply { put("file", fileParam) }
                                        val res2 = connectionManager.requestCapability("voice.preview_audio", req2)
                                        
                                        val b64 = res2.optString("audio_b64", "")
                                        if (b64.isNotEmpty()) {
                                            val tempFile = File.createTempFile("preview", ".wav", context.cacheDir)
                                            tempFile.writeBytes(Base64.decode(b64, Base64.DEFAULT))
                                            val player = MediaPlayer()
                                            player.setDataSource(tempFile.absolutePath)
                                            player.prepare()
                                            player.start()
                                            switchMessage = "Playing preview..."
                                        } else {
                                            switchMessage = "Preview failed: missing audio data"
                                        }
                                    } else {
                                        switchMessage = "Preview failed: ${res1.optString("error")}"
                                    }
                                } catch (e: Exception) {
                                    switchMessage = "Preview error: ${e.message}"
                                }
                            }
                        }
                    )
                }
            }
            Spacer(modifier = Modifier.height(16.dp))
            
            // Hold to Talk button
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(60.dp)
                    .clip(RoundedCornerShape(30.dp))
                    .background(if (isRecording) Pink else Purple)
                    .pointerInput(Unit) {
                        detectTapGestures(
                            onPress = {
                                isRecording = true
                                val job = scope.launch(Dispatchers.IO) {
                                    var audioRecord: AudioRecord? = null
                                    val sampleRate = 16000
                                    try {
                                        audioRecord = AudioRecord(
                                            MediaRecorder.AudioSource.MIC,
                                            sampleRate,
                                            AudioFormat.CHANNEL_IN_MONO,
                                            AudioFormat.ENCODING_PCM_16BIT,
                                            AudioRecord.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT) * 2
                                        )
                                        audioRecord.startRecording()
                                        val buffer = ByteArray(4096)
                                        while (isRecording) {
                                            val read = audioRecord.read(buffer, 0, buffer.size)
                                            if (read > 0) {
                                                val chunk = buffer.copyOf(read)
                                                val b64 = Base64.encodeToString(chunk, Base64.NO_WRAP)
                                                val req = JSONObject().apply {
                                                    put("audio_b64", b64)
                                                    put("sample_rate", sampleRate)
                                                    put("is_final", false)
                                                }
                                                connectionManager.requestCapability("audio.stream", req)
                                            }
                                        }
                                        // End of recording
                                        val reqFinal = JSONObject().apply {
                                            put("is_final", true)
                                            put("sample_rate", sampleRate)
                                        }
                                        val sttRes = connectionManager.requestCapability("audio.stream", reqFinal)
                                        val text = sttRes.optJSONObject("payload")?.optString("text") ?: ""
                                        if (text.isNotBlank()) {
                                            val chatReq = JSONObject().apply { put("message", text) }
                                            connectionManager.requestCapability("conversation.chat", chatReq)
                                        }
                                    } catch (e: Exception) {
                                    } finally {
                                        audioRecord?.stop()
                                        audioRecord?.release()
                                    }
                                }
                                tryAwaitRelease()
                                isRecording = false
                            }
                        )
                    },
                contentAlignment = Alignment.Center
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.Add, contentDescription = null, tint = Color.White) // Replaced Mic to avoid missing extended icons dependency
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(if (isRecording) "Listening... Release to send" else "Hold to Talk to Vivy", color = Color.White, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun VoiceIdentityCard(voice: VoiceIdentity, onSwitch: () -> Unit, onPreview: () -> Unit) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Card),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier.size(42.dp)
                    .background(
                        Brush.linearGradient(listOf(Purple, Pink)),
                        RoundedCornerShape(21.dp)
                    )
                    .clickable { onPreview() },
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Filled.PlayArrow, contentDescription = "Preview",
                    tint = Color.White, modifier = Modifier.size(20.dp))
            }
            Spacer(Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(voice.name, color = Color.White, fontWeight = FontWeight.Medium)
                Text(voice.language ?: "en", color = Color(0xFF64748B), fontSize = 12.sp)
            }
            if (voice.active == true) {
                Text("ACTIVE", color = Color(0xFF22C55E), fontSize = 10.sp, fontWeight = FontWeight.Bold)
            } else {
                TextButton(onClick = onSwitch) {
                    Text("Use", color = Purple)
                }
            }
        }
    }
}
