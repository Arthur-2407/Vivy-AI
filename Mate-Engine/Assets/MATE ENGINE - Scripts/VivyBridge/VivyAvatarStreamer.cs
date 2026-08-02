using UnityEngine;
using System;
using System.Collections;
using System.Reflection;

/// <summary>
/// Vivy Avatar Streamer — Captures the avatar face/body using a spawned Camera and sends
/// JPEG frames to Vivy's Python backend (avatar_bridge.py) via WebSocket client.
///
/// Optimization changelog (non-destructive):
///   - Default resolution upgraded: 320×320 → 640×640  (Inspector-configurable)
///   - Default FPS upgraded: 5 → 24, range expanded [1..30]  (Inspector-configurable)
///   - JPEG quality upgraded: 70 → 90  (Inspector-configurable)
///   - RenderTexture depth upgraded: 16-bit → 24-bit for accurate depth testing
///   - Stream camera MSAA enabled (antiAliasing = 4) for cleaner edges pre-encode
///   - Texture2D upgraded: RGB24 → RGBA32 to match ARGB32 RenderTexture source
///     (avoids internal format conversion overhead on ReadPixels)
///   - Added enableStreaming toggle. Set to false in the Inspector to disable entirely.
///   - Camera is lazily spawned on first LateUpdate when connected and enabled,
///     not unconditionally in Start(). Prevents dangling camera when WS not running.
///   - Frame sending is skipped when disconnected.
///
/// Upgraded optimizations (v2):
///   - Async GPU Readback (no main-thread blocking on CPU-GPU sync)
///   - Offloaded Base64 conversion and socket transmission to background Task thread
///   - Added dynamic viewport-driven aspect ratio & resolution resizing (ResizeStream)
///   - Automatic camera framing centering on the Avatar Head bone with lookAt
///   - URP Additional Camera Data injection via reflection (PostProcessing & MSAA enabled)
///   - Configurable renderScale multiplier
/// </summary>
public class VivyAvatarStreamer : MonoBehaviour
{
    [Header("Stream Resolution")]
    public int width  = 640;
    public int height = 640;

    [Header("Resolution Scale")]
    [Range(0.25f, 2.0f)] public float renderScale = 1.0f;

    [Header("Framerate Control")]
    [Range(1f, 90f)] public float fps = 60f; // Range expanded to [1..90], default upgraded to 60

    [Header("Encoding Quality")]
    /// <summary>
    /// JPEG encoding quality [1–100]. Higher = sharper image, larger payload.
    /// 90 is the recommended balance for a localhost WebSocket stream.
    /// </summary>
    [Range(1, 100)] public int jpegQuality = 90;

    [Header("Camera Configuration")]
    public float   fieldOfView   = 35f;
    // Offset relative to the avatar root. Pointing back (Euler 180 Y) towards the avatar.
    public Vector3 cameraOffset  = new Vector3(0f, 1.4f, 1.2f);

    [Header("Dynamic Camera Adjustments")]
    public float zoom = 1.0f;
    public float yaw = 0.0f;
    public float pitch = 0.0f;
    public float panX = 0.0f;
    public float panY = 0.0f;

    [Header("Streaming")]
    /// <summary>
    /// Master enable switch. Disable to skip camera spawn and frame capture entirely.
    /// Can be toggled at runtime without breaking any other system.
    /// </summary>
    public bool enableStreaming = true;

    private Camera             _streamCam;
    public Camera StreamCamera => _streamCam;
    private RenderTexture      _rt;
    private Texture2D          _tex;
    private VivyWebSocketClient _wsClient;
    private float              _nextFrameTime;
    private bool               _cameraReady;
    private int                _frameCount; // Telemetry frame counter
    private bool               _isProcessingFrame; // Async lock flag
    private float              _lastFrameStartTime; // Auto-recovery timestamp
    private Animator           _lastAnimator;
    private float              _currentFocusFactor = 0f;

    void Start()
    {
        _wsClient = GetComponent<VivyWebSocketClient>();
        // Camera is spawned lazily in LateUpdate to avoid wasting resources
        // when the WebSocket server (avatar_bridge.py) is not running.
    }

    void LateUpdate()
    {
        if (!enableStreaming || !gameObject.activeInHierarchy || !enabled) return;
        if (_wsClient == null || !_wsClient.IsConnected) return;

        // Auto-recover if an async GPU readback or background encoding task hangs for > 1.0 second
        if (_isProcessingFrame && Time.time - _lastFrameStartTime > 1.0f)
        {
            _isProcessingFrame = false;
        }

        // Lazy camera initialisation — only runs once after first connection
        if (!_cameraReady)
        {
            SpawnCamera();
            _cameraReady = true;
        }

        // Keep framing aligned to Head bone if animator changes
        var currentAnimator = GetComponent<Animator>();
        if (currentAnimator != _lastAnimator)
        {
            _lastAnimator = currentAnimator;
        }

        // Smoothly interpolate focus factor over time for transitions
        bool isFocusMode = false;
        foreach (var handler in AvatarBigScreenHandler.ActiveHandlers)
        {
            if (handler.IsBigScreenActive)
            {
                isFocusMode = true;
                break;
            }
        }
        float targetFactor = isFocusMode ? 1f : 0f;
        _currentFocusFactor = Mathf.MoveTowards(_currentFocusFactor, targetFactor, Time.deltaTime * 3.5f);

        // Recalculate camera position and zoom every frame for smooth interpolation and look-at
        AdjustCameraFraming();

        if (Time.time >= _nextFrameTime && !_isProcessingFrame)
        {
            _nextFrameTime = Time.time + (1f / fps);
            _isProcessingFrame = true;
            _lastFrameStartTime = Time.time;
            StartCoroutine(CaptureAndSendAsync());
        }
    }

    private void SpawnCamera()
    {
        GameObject camObj = new GameObject("VivyStreamCamera");
        camObj.transform.SetParent(transform, false);
        
        _streamCam = camObj.AddComponent<Camera>();
        _streamCam.clearFlags       = CameraClearFlags.SolidColor;
        // Dark background matching the premium web dashboard aesthetic
        _streamCam.backgroundColor  = new Color(0.035f, 0.027f, 0.082f, 1f);
        _streamCam.fieldOfView      = fieldOfView;

        // Apply dynamic head framing
        AdjustCameraFraming();

        // Safe URP Configuration
        ConfigureURPCamera(_streamCam);
        if (Camera.main != null)
        {
            SyncURPCameraData(Camera.main, _streamCam);
        }

        // Optimisation: 24-bit depth buffer for accurate depth sorting at higher resolutions.
        // MSAA x4 on the capture RenderTexture produces cleaner edges before JPEG encoding,
        // reducing the visual impact of compression artifacts on hair and fine details.
        int targetW = Mathf.RoundToInt(width * renderScale);
        int targetH = Mathf.RoundToInt(height * renderScale);
        _rt = new RenderTexture(targetW, targetH, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
        _rt.antiAliasing = 4;
        _streamCam.targetTexture = _rt;

        // Optimisation: RGBA32 matches the ARGB32 source format — Unity converts on ReadPixels
        // when source and target formats differ. Using a compatible format avoids an extra
        // internal blit/conversion pass on each capture.
        _tex = new Texture2D(targetW, targetH, TextureFormat.RGBA32, false);

        if (_wsClient != null && _wsClient.logMessages)
            Debug.Log($"[VivyStreamer] Stream camera spawned — Res: {targetW}×{targetH} | FPS: {fps} | JPEG Q: {jpegQuality} | MSAA: {_rt.antiAliasing}x");
    }

    public void SetCameraControl(float z, float y, float p, float px, float py)
    {
        zoom = z;
        yaw = y;
        pitch = p;
        panX = px;
        panY = py;
        AdjustCameraFraming();
    }

    private void AdjustCameraFraming()
    {
        if (_streamCam == null) return;

        float headHeight = 1.4f;
        var anim = GetComponent<Animator>();
        if (anim != null && anim.isHuman)
        {
            Transform head = anim.GetBoneTransform(HumanBodyBones.Head);
            if (head != null)
            {
                headHeight = transform.InverseTransformPoint(head.position).y;
            }
        }

        float scale = transform.lossyScale.y;
        Camera mainCam = Camera.main;

        if (mainCam != null)
        {
            // Sync camera configuration and rendering properties from authoritative Camera.main
            _streamCam.orthographic = mainCam.orthographic;
            _streamCam.orthographicSize = mainCam.orthographicSize;
            _streamCam.nearClipPlane = mainCam.nearClipPlane;
            _streamCam.farClipPlane = mainCam.farClipPlane;
            _streamCam.cullingMask = mainCam.cullingMask;
            _streamCam.clearFlags = mainCam.clearFlags;
            _streamCam.backgroundColor = mainCam.backgroundColor;
            _streamCam.allowHDR = mainCam.allowHDR;
            _streamCam.allowMSAA = mainCam.allowMSAA;
            _streamCam.renderingPath = mainCam.renderingPath;
            _streamCam.usePhysicalProperties = mainCam.usePhysicalProperties;
            _streamCam.sensorSize = mainCam.sensorSize;
            _streamCam.lensShift = mainCam.lensShift;
            _streamCam.gateFit = mainCam.gateFit;

            // Sync URP Additional Camera Data dynamically
            SyncURPCameraData(mainCam, _streamCam);

            // Calculate look-at target point along Main Camera's forward vector at the avatar's distance
            float baseDistance = Vector3.Distance(mainCam.transform.position, transform.position);
            Vector3 targetPoint = mainCam.transform.position + mainCam.transform.forward * baseDistance;
            Quaternion baseRotation = mainCam.transform.rotation;
            float targetFOV = mainCam.fieldOfView;

            // Apply zoom as FOV scaling
            _streamCam.fieldOfView = Mathf.Clamp(targetFOV / zoom, 5f, 90f);

            // Combine base rotation with local browser orbit offsets
            Quaternion extraRotation = Quaternion.Euler(pitch, yaw, 0f);
            Quaternion finalRotation = baseRotation * extraRotation;

            // Apply browser offsets (zoom scales the camera distance relative to look-at target)
            float finalDistance = baseDistance / zoom;
            Vector3 localOffset = finalRotation * Vector3.back * finalDistance;
            Vector3 panOffset = finalRotation * new Vector3(panX, panY, 0f) * scale;

            _streamCam.transform.position = targetPoint + localOffset + panOffset;
            _streamCam.transform.rotation = finalRotation;
        }
        else
        {
            // Fallback to local default framing if Camera.main is absent
            float targetZ = Mathf.Lerp(cameraOffset.z, 0.45f, _currentFocusFactor) * scale;
            float targetYOffset = Mathf.Lerp(cameraOffset.y, 1.4f, _currentFocusFactor);
            float targetFOV = Mathf.Lerp(fieldOfView, 25f, _currentFocusFactor);
            float targetPitchOffset = Mathf.Lerp(5f, 0f, _currentFocusFactor);

            _streamCam.fieldOfView = Mathf.Clamp(targetFOV / zoom, 5f, 90f);

            Quaternion rotation = Quaternion.Euler(targetPitchOffset + pitch, 180f + yaw, 0f);
            Vector3 rotatedOffset = rotation * Vector3.forward * targetZ;

            _streamCam.transform.localPosition = new Vector3(cameraOffset.x + panX, headHeight + (targetYOffset - 1.4f) + panY, 0f) + rotatedOffset;
            
            Vector3 targetLookAt = transform.TransformPoint(new Vector3(cameraOffset.x + panX, headHeight + (targetYOffset - 1.4f) + panY, 0f));
            _streamCam.transform.LookAt(targetLookAt);
        }
    }

    private void ConfigureURPCamera(Camera cam)
    {
        try
        {
            var uacdType = Type.GetType("UnityEngine.Rendering.Universal.UniversalAdditionalCameraData, Unity.RenderPipelines.Universal.Runtime");
            if (uacdType != null)
            {
                var comp = cam.gameObject.GetComponent(uacdType);
                if (comp == null)
                {
                    comp = cam.gameObject.AddComponent(uacdType);
                }

                if (comp != null)
                {
                    // Enable post-processing on the stream camera
                    var renderPostProcessingProp = uacdType.GetProperty("renderPostProcessing", BindingFlags.Public | BindingFlags.Instance);
                    if (renderPostProcessingProp != null)
                    {
                        renderPostProcessingProp.SetValue(comp, true, null);
                    }

                    // Enable shadow rendering
                    var renderShadowsProp = uacdType.GetProperty("renderShadows", BindingFlags.Public | BindingFlags.Instance);
                    if (renderShadowsProp != null)
                    {
                        renderShadowsProp.SetValue(comp, true, null);
                    }

                    // Enable MSAA
                    var allowMSAAProp = uacdType.GetProperty("allowMSAA", BindingFlags.Public | BindingFlags.Instance);
                    if (allowMSAAProp != null)
                    {
                        allowMSAAProp.SetValue(comp, true, null);
                    }

                    Debug.Log("[VivyStreamer] Configured URP Additional Camera Data (PostProcessing: true, Shadows: true, MSAA: true)");
                }
            }
        }
        catch (Exception ex)
        {
            Debug.LogWarning("[VivyStreamer] Could not configure URP camera data: " + ex.Message);
        }
    }

    private void SyncURPCameraData(Camera sourceCam, Camera destCam)
    {
        try
        {
            var uacdType = Type.GetType("UnityEngine.Rendering.Universal.UniversalAdditionalCameraData, Unity.RenderPipelines.Universal.Runtime");
            if (uacdType != null)
            {
                var sourceComp = sourceCam.gameObject.GetComponent(uacdType);
                var destComp = destCam.gameObject.GetComponent(uacdType);
                if (sourceComp != null && destComp != null)
                {
                    foreach (var prop in uacdType.GetProperties(BindingFlags.Public | BindingFlags.Instance))
                    {
                        if (prop.CanRead && prop.CanWrite && prop.Name != "cameraStack")
                        {
                            try
                            {
                                prop.SetValue(destComp, prop.GetValue(sourceComp, null), null);
                            }
                            catch { }
                        }
                    }
                }
            }
        }
        catch (Exception ex)
        {
            Debug.LogWarning("[VivyStreamer] Error syncing URP additional camera data: " + ex.Message);
        }
    }

    public void ResizeStream(int w, int h)
    {
        if (w <= 0 || h <= 0) return;
        if (w > 2048 || h > 2048) { w = 2048; h = 2048; } // Cap at 2K for performance
        if (w == width && h == height && _rt != null) return;

        width = w;
        height = h;

        int targetW = Mathf.RoundToInt(width * renderScale);
        int targetH = Mathf.RoundToInt(height * renderScale);

        // Recreate resources on the main thread
        if (_rt != null)
        {
            _rt.Release();
            Destroy(_rt);
        }
        if (_tex != null)
        {
            Destroy(_tex);
        }

        _rt = new RenderTexture(targetW, targetH, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
        _rt.antiAliasing = 4;
        if (_streamCam != null)
        {
            _streamCam.targetTexture = _rt;
            AdjustCameraFraming(); // Recalculate framing/matrix on aspect resize
        }

        _tex = new Texture2D(targetW, targetH, TextureFormat.RGBA32, false);

        if (_wsClient != null && _wsClient.logMessages)
            Debug.Log($"[VivyStreamer] Stream resized dynamically to {targetW}×{targetH} (renderScale: {renderScale})");
    }

    private IEnumerator CaptureAndSendAsync()
    {
        yield return new WaitForEndOfFrame();

        // Guard: streaming may have been disabled or WS disconnected mid-frame
        if (!enableStreaming || _wsClient == null || !_wsClient.IsConnected || _rt == null)
        {
            _isProcessingFrame = false;
            yield break;
        }

        // Ensure camera explicitly renders the newest avatar animation pose into the target RenderTexture before readback
        if (_streamCam != null && _streamCam.enabled)
        {
            _streamCam.Render();
        }

        // Request async GPU readback to avoid blocking main thread
        UnityEngine.Rendering.AsyncGPUReadback.Request(_rt, 0, TextureFormat.RGBA32, (request) => {
            try
            {
                if (request.hasError || !enableStreaming || _wsClient == null || !_wsClient.IsConnected || _rt == null)
                {
                    _isProcessingFrame = false;
                    return;
                }

                // GUARD: Race condition fix. If the stream was resized while the async readback 
                // was in flight, the pixel data length won't match the new _tex dimensions.
                if (request.width != _tex.width || request.height != _tex.height)
                {
                    _isProcessingFrame = false;
                    return;
                }

                // Copy texture data from GPU to CPU memory
                var pixelData = request.GetData<byte>();
                _tex.LoadRawTextureData(pixelData);
                _tex.Apply();

                // Encode raw bytes to JPG (must run on main thread)
                byte[] jpgBytes = _tex.EncodeToJPG(jpegQuality);

                // Offload Base64 encoding and WebSocket write to thread pool worker thread
                System.Threading.Tasks.Task.Run(() => {
                    try
                    {
                        string base64 = Convert.ToBase64String(jpgBytes);
                        string payload = "{\"type\":\"frame\",\"data\":\"" + base64 + "\"}";
                        _wsClient.SendRawPayload(payload);
                    }
                    catch (Exception ex)
                    {
                        Debug.LogWarning("[VivyStreamer] Worker send exception: " + ex.Message);
                    }
                    finally
                    {
                        _isProcessingFrame = false;
                    }
                });
            }
            catch (Exception ex)
            {
                Debug.LogError("[VivyStreamer] Readback callback exception: " + ex.Message);
                _isProcessingFrame = false;
            }
        });
    }

    void OnEnable()
    {
        if (_streamCam != null) _streamCam.enabled = true;
        _isProcessingFrame = false;
    }

    void OnDisable()
    {
        if (_streamCam != null) _streamCam.enabled = false;
        _isProcessingFrame = false;
    }

    void OnDestroy()
    {
        if (_rt  != null) _rt.Release();
        if (_tex != null) Destroy(_tex);
        if (_streamCam != null) Destroy(_streamCam.gameObject);
    }
}
