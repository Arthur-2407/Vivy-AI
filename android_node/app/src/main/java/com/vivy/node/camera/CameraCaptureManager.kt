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
import androidx.camera.core.Preview

class CameraCaptureManager(
    private val context: Context,
    private val connectionManager: HubConnectionManager
) {
    private var cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()
    private var lastFrameTime = 0L

    fun startCamera(surfaceProvider: Preview.SurfaceProvider? = null) {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)

        cameraProviderFuture.addListener({
            val cameraProvider: ProcessCameraProvider = cameraProviderFuture.get()

            val preview = Preview.Builder().build()
            if (surfaceProvider != null) {
                preview.setSurfaceProvider(surfaceProvider)
            }

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
                if (surfaceProvider != null) {
                    cameraProvider.bindToLifecycle(
                        context as LifecycleOwner, cameraSelector, preview, imageAnalyzer
                    )
                } else {
                    cameraProvider.bindToLifecycle(
                        context as LifecycleOwner, cameraSelector, imageAnalyzer
                    )
                }
            } catch (exc: Exception) {
                exc.printStackTrace()
            }

        }, ContextCompat.getMainExecutor(context))
    }

    fun stopCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()
            cameraProvider.unbindAll()
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
