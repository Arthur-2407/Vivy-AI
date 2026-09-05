package com.vivy.node.camera

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Base64
import com.vivy.node.connection.HubConnectionManager
import kotlinx.coroutines.*
import org.json.JSONObject

class AudioStreamManager(
    private val connectionManager: HubConnectionManager
) {
    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    private val sampleRate = 16000
    private var recordingJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    @SuppressLint("MissingPermission")
    fun startStreaming() {
        if (isRecording) return

        val bufferSize = AudioRecord.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )

        if (bufferSize == AudioRecord.ERROR || bufferSize == AudioRecord.ERROR_BAD_VALUE) {
            return
        }

        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            bufferSize * 2
        )

        if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
            return
        }

        audioRecord?.startRecording()
        isRecording = true

        recordingJob = scope.launch {
            val buffer = ByteArray(bufferSize)
            while (isRecording && isActive) {
                val readResult = audioRecord?.read(buffer, 0, buffer.size) ?: 0
                if (readResult > 0) {
                    val validData = buffer.copyOfRange(0, readResult)
                    val base64Audio = Base64.encodeToString(validData, Base64.NO_WRAP)
                    
                    val payload = JSONObject().apply {
                        put("audio_b64", base64Audio)
                        put("sample_rate", sampleRate)
                        put("is_final", false)
                    }
                    connectionManager.sendCapabilityRequest("audio.stream", payload)
                }
            }
        }
    }

    fun stopStreaming() {
        if (!isRecording) return
        isRecording = false
        recordingJob?.cancel()
        
        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (e: Exception) {
            // Ignore
        } finally {
            audioRecord = null
        }

        // Send final chunk to trigger transcription
        val payload = JSONObject().apply {
            put("audio_b64", "") // Empty chunk
            put("sample_rate", sampleRate)
            put("is_final", true)
        }
        scope.launch {
            connectionManager.sendCapabilityRequest("audio.stream", payload)
        }
    }
}
