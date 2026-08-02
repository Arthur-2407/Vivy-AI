using UnityEngine;
using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Net.WebSockets;
using System.Collections;
using System.Collections.Generic;

/// <summary>
/// Vivy WebSocket Client — Connects to Vivy's Python avatar_bridge.py
/// Receives emotion, animation, speak, blendshape, lookAt, and status commands.
/// Routes them to VivyEmotionMapper, VivyLipSync, AvatarMouseTracking components.
///
/// Attach this to the root avatar GameObject (same object as AvatarAnimatorController).
///
/// Changes from v1:
///   - Fixed silent message truncation: receive buffer now accumulates fragments
///     correctly via MemoryStream + EndOfMessage flag (was a hard 4096-byte limit).
///   - Added HasParameter guard on animation trigger to prevent silent log spam.
///   - Wired status handler: thinking/speaking/ready drive Animator bools when
///     the controller has the matching parameters (safe no-op if absent).
///   - Added AvatarMouseTracking reference for lookAt routing (Phase 2A wires this).
/// </summary>
public class VivyWebSocketClient : MonoBehaviour
{
    [Header("Connection Settings")]
    public string serverUri = "ws://127.0.0.1:8765";
    public float reconnectDelay = 3f;
    public bool autoConnect = true;
    public bool logMessages = true;

    [Header("References (Auto-resolved if null)")]
    public VivyEmotionMapper emotionMapper;
    public VivyLipSync lipSync;
    public Animator animator;
    public AvatarMouseTracking mouseTracking;

    // Optional Animator parameter names for status routing.
    // These are only applied if the Animator controller has these parameters.
    // Leave empty to disable the corresponding status routing.
    [Header("Status Animator Parameters (optional)")]
    public string thinkingParam  = "isThinking";
    public string speakingParam  = "isSpeaking";

    // Connection state
    private ClientWebSocket _ws;
    private CancellationTokenSource _cts;
    private Task _receiveTask;  // Repair B: was Thread — Task allows proper exception propagation
    private bool _connected;
    private bool _shouldReconnect = true;

    // Thread-safe message queue (Unity is single-threaded for API calls)
    private readonly Queue<string> _messageQueue = new Queue<string>();
    private readonly object _queueLock = new object();
    private readonly object _sendLock = new object();

    private SyncPoseData _latestSyncPose = null;

    public static event Action<string> OnSpeakReceived;

    void Start()
    {
        // Auto-resolve references
        if (emotionMapper  == null) emotionMapper  = GetComponent<VivyEmotionMapper>();
        if (lipSync        == null) lipSync        = GetComponent<VivyLipSync>();
        if (animator       == null) animator       = GetComponent<Animator>();
        if (mouseTracking  == null) mouseTracking  = GetComponent<AvatarMouseTracking>();

        if (GetComponent<VivyRuntimeAnimationBuilder>() == null)
        {
            gameObject.AddComponent<VivyRuntimeAnimationBuilder>();
            Debug.Log("[VivyWS] Dynamically added VivyRuntimeAnimationBuilder to WebSocketClient GameObject.");
        }

        if (autoConnect)
            Connect();
    }

    void Update()
    {
        // Process queued messages on the main thread
        List<string> messagesToProcess = null;
        lock (_queueLock)
        {
            if (_messageQueue.Count > 0)
            {
                messagesToProcess = new List<string>(_messageQueue);
                _messageQueue.Clear();
            }
        }

        if (messagesToProcess != null)
        {
            int latestLookAtIndex = -1;
            int latestCameraIndex = -1;

            for (int i = 0; i < messagesToProcess.Count; i++)
            {
                string rawJson = messagesToProcess[i];
                if (rawJson.Contains("\"type\":\"lookAt\""))
                {
                    latestLookAtIndex = i;
                }
                else if (rawJson.Contains("\"type\":\"camera\""))
                {
                    latestCameraIndex = i;
                }
            }

            for (int i = 0; i < messagesToProcess.Count; i++)
            {
                string rawJson = messagesToProcess[i];
                bool isLookAt = rawJson.Contains("\"type\":\"lookAt\"");
                bool isCamera = rawJson.Contains("\"type\":\"camera\"");

                if (isLookAt && i != latestLookAtIndex)
                {
                    continue; // Skip obsolete lookAt
                }
                if (isCamera && i != latestCameraIndex)
                {
                    continue; // Skip obsolete camera
                }

                ProcessMessage(rawJson);
            }
        }
    }

    void LateUpdate()
    {
        if (_latestSyncPose != null && _latestSyncPose.bones != null && animator != null && animator.IsValidAndPlaying())
        {
            foreach (var bp in _latestSyncPose.bones)
            {
                if (Enum.TryParse<HumanBodyBones>(bp.name, out HumanBodyBones boneType))
                {
                    Transform bone = animator.GetBoneTransform(boneType);
                    if (bone != null)
                    {
                        bone.localRotation = new Quaternion(bp.x, bp.y, bp.z, bp.w);
                    }
                }
            }
            // Clear it after applying so it doesn't freeze the avatar when streaming stops
            _latestSyncPose = null;
        }
    }

    void OnDestroy()
    {
        _shouldReconnect = false;
        Disconnect();
    }

    void OnApplicationQuit()
    {
        _shouldReconnect = false;
        Disconnect();
    }

    // =====================================================
    // CONNECTION MANAGEMENT
    // =====================================================
    public void Connect()
    {
        if (_connected) return;
        if (logMessages)
            Debug.Log($"[VivyWS] Socket State Changed: Connecting to {serverUri}...");
        _cts = new CancellationTokenSource();
        // Repair B: Task.Run starts ReceiveLoop on the thread-pool and stores the Task so
        // exceptions are observable (not fire-and-forget).  Behaviour is identical to the
        // previous Thread approach in the happy path.
        _receiveTask = Task.Run(() => ReceiveLoop(), _cts.Token);
    }

    public void Disconnect()
    {
        if (logMessages)
            Debug.Log("[VivyWS] Socket State Changed: Disconnecting...");
        _cts?.Cancel();
        try
        {
            if (_ws != null && _ws.State == WebSocketState.Open)
                _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "Closing", CancellationToken.None).Wait(1000);
        }
        catch { }
        _ws?.Dispose();
        _ws = null;
        _connected = false;
        if (logMessages)
            Debug.Log("[VivyWS] Socket State Changed: Disconnected.");
    }

    // =====================================================
    // RECEIVE LOOP — Fragment-safe accumulator
    // Fixes GAP 6: old code used a fixed 4096-byte buffer and called ReceiveAsync
    // exactly once per message.  WebSocket messages can span multiple fragments
    // (EndOfMessage == false).  Large payloads (e.g. base64 JPEG frames ~30 KB)
    // were silently truncated, producing malformed JSON on the Python side.
    // The new implementation accumulates fragments into a MemoryStream until
    // EndOfMessage == true, then decodes the whole message as a single string.
    // =====================================================
    // Repair B: async Task (was async void) — exceptions propagate through _receiveTask
    private async Task ReceiveLoop()
    {
        // Fragment buffer: 16 KB chunks.  MemoryStream grows as needed.
        const int chunkSize = 16 * 1024;
        var chunkBuffer = new byte[chunkSize];

        while (_shouldReconnect && !_cts.IsCancellationRequested)
        {
            try
            {
                _ws = new ClientWebSocket();
                await _ws.ConnectAsync(new Uri(serverUri), _cts.Token);
                _connected = true;

                if (logMessages)
                    Debug.Log($"[VivyWS] Connected to {serverUri}");

                // Send ready message
                string readyMsg = "{\"type\":\"ready\"}";
                var readyBytes = Encoding.UTF8.GetBytes(readyMsg);
                await _ws.SendAsync(new ArraySegment<byte>(readyBytes), WebSocketMessageType.Text, true, _cts.Token);

                // Receive loop — accumulate fragments
                while (_ws.State == WebSocketState.Open && !_cts.IsCancellationRequested)
                {
                    using var ms = new MemoryStream();
                    WebSocketReceiveResult result;

                    do
                    {
                        result = await _ws.ReceiveAsync(new ArraySegment<byte>(chunkBuffer), _cts.Token);

                        if (result.MessageType == WebSocketMessageType.Close)
                        {
                            if (logMessages) Debug.Log("[VivyWS] Server closed connection.");
                            goto exitReceive;
                        }

                        if (result.MessageType == WebSocketMessageType.Text)
                            ms.Write(chunkBuffer, 0, result.Count);

                    } while (!result.EndOfMessage);

                    if (result.MessageType == WebSocketMessageType.Text)
                    {
                        string message = Encoding.UTF8.GetString(ms.GetBuffer(), 0, (int)ms.Length);
                        lock (_queueLock)
                        {
                            _messageQueue.Enqueue(message);
                        }
                    }
                }
                exitReceive:;
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                if (logMessages)
                    Debug.LogWarning($"[VivyWS] Connection error: {ex.Message}");
            }
            finally
            {
                _connected = false;
                _ws?.Dispose();
                _ws = null;
            }

            // Reconnect delay — await Task.Delay instead of Thread.Sleep so the async
            // method yields correctly and does not block a thread-pool thread.
            if (_shouldReconnect && !_cts.IsCancellationRequested)
            {
                if (logMessages) Debug.Log($"[VivyWS] Reconnecting in {reconnectDelay}s...");
                await Task.Delay((int)(reconnectDelay * 1000), _cts.Token).ConfigureAwait(false);
            }
        }
    }

    // =====================================================
    // SEND TO PYTHON (Unity → Vivy)
    // =====================================================
    public void SendInteraction(string action)
    {
        if (!_connected || _ws == null || _ws.State != WebSocketState.Open) return;
        string msg = $"{{\"type\":\"interaction\",\"action\":\"{action}\"}}";
        var bytes = Encoding.UTF8.GetBytes(msg);
        lock (_sendLock)
        {
            try
            {
                _ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _cts.Token).Wait();
            }
            catch { }
        }
    }

    public void SendRawPayload(string payload)
    {
        if (!_connected || _ws == null || _ws.State != WebSocketState.Open) return;
        var bytes = Encoding.UTF8.GetBytes(payload);
        lock (_sendLock)
        {
            try
            {
                _ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _cts.Token).Wait();
            }
            catch { }
        }
    }

    // =====================================================
    // MESSAGE ROUTING (runs on main thread via Update)
    // =====================================================
    private void ProcessMessage(string rawJson)
    {
        if (logMessages) Debug.Log($"[VivyWS] Received: {rawJson}");

        try
        {
            var data = JsonUtility.FromJson<VivyMessage>(rawJson);
            if (data == null) return;

            switch (data.type)
            {
                case "emotion":
                    if (emotionMapper != null)
                        emotionMapper.SetEmotion(data.value);
                    break;

                case "emotion_state":
                    HandleEmotionState(rawJson);
                    break;

                case "animation":
                    HandleAnimation(data.value);
                    break;

                case "speak":
                    if (lipSync != null)
                        lipSync.StartLipSync(data.text);
                    OnSpeakReceived?.Invoke(data.text);
                    break;

                case "blendshape":
                    if (emotionMapper != null)
                        emotionMapper.SetBlendshapeDirect(data.name, data.weight);
                    break;

                case "lookAt":
                    HandleLookAt(data.x, data.y, data.duration);
                    break;

                case "load_avatar":
                    HandleLoadAvatar(data.value);
                    break;

                case "status":
                    HandleStatus(data.value);
                    break;

                case "resize":
                    HandleResize(data.width, data.height);
                    break;

                case "camera":
                    HandleCameraControl(data.zoom, data.yaw, data.pitch, data.panX, data.panY);
                    break;

                case "interaction":
                    HandleInteraction(data.action, data.name, data.state, data.value);
                    break;

                case "circadian":
                    HandleCircadian(data.energy, data.phase);
                    break;

                case "sync_pose":
                    HandleSyncPose(rawJson);
                    break;

                default:
                    if (logMessages)
                        Debug.Log($"[VivyWS] Unknown message type: {data.type}");
                    break;
            }
        }
        catch (Exception ex)
        {
            Debug.LogWarning($"[VivyWS] Failed to parse message: {ex.Message}");
        }
    }

    private void HandleCameraControl(float z, float y, float p, float px, float py)
    {
        var streamer = GetComponent<VivyAvatarStreamer>();
        if (streamer != null)
        {
            streamer.SetCameraControl(z, y, p, px, py);
        }
    }

    private void HandleInteraction(string action, string name, bool state, string value)
    {
        if (string.IsNullOrEmpty(action)) return;

        switch (action.ToLower().Trim())
        {
            case "chibi":
                foreach (var chibi in GameObject.FindObjectsByType<ChibiToggle>(FindObjectsInactive.Exclude, FindObjectsSortMode.None))
                {
                    chibi.ToggleChibiMode();
                }
                break;

            case "accessory":
                foreach (var handler in AccessoiresHandler.ActiveHandlers)
                {
                    foreach (var rule in handler.rules)
                    {
                        if (rule.ruleName.Equals(name, StringComparison.OrdinalIgnoreCase))
                        {
                            rule.isEnabled = state;
                            break;
                        }
                    }
                }
                break;

            case "unsnap":
                foreach (var h in GameObject.FindObjectsByType<AvatarWindowHandler>(FindObjectsInactive.Exclude, FindObjectsSortMode.None))
                {
                    h.ForceExitWindowSitting();
                }
                break;

            case "bigscreen":
                foreach (var handler in AvatarBigScreenHandler.ActiveHandlers)
                {
                    handler.ToggleBigScreenFromUI();
                }
                break;

            case "dance":
                var controller = GetComponent<AvatarAnimatorController>();
                if (controller != null)
                {
                    controller.SetDancingOverride(state);
                }
                else
                {
                    if (animator != null && animator.IsValidAndPlaying())
                    {
                        animator.SetBool("isDancing", state);
                    }
                }
                break;

            case "sleep":
                var sleepController = GetComponent<AvatarSleepController>();
                if (sleepController != null)
                {
                    sleepController.SetSleepOverride(state);
                }
                else
                {
                    if (animator != null && animator.IsValidAndPlaying())
                    {
                        if (AnimatorHasParameter("isSleeping", AnimatorControllerParameterType.Bool))
                            animator.SetBool("isSleeping", state);
                        else if (AnimatorHasParameter("IsSleeping", AnimatorControllerParameterType.Bool))
                            animator.SetBool("IsSleeping", state);
                    }
                }
                break;

            case "drag_start":
                if (animator != null && AnimatorHasParameter("isDragging", AnimatorControllerParameterType.Bool))
                {
                    animator.SetBool("isDragging", true);
                }
                break;

            case "drag_stop":
                if (animator != null && AnimatorHasParameter("isDragging", AnimatorControllerParameterType.Bool))
                {
                    animator.SetBool("isDragging", false);
                }
                break;

            case "animation":
                if (!string.IsNullOrEmpty(value))
                {
                    HandleAnimation(value);
                }
                break;

            case "gear_request":
                SendGearStates();
                break;

            case "gear_select":
                if (value == "accessory")
                {
                    foreach (var handler in AccessoiresHandler.ActiveHandlers)
                    {
                        foreach (var rule in handler.rules)
                        {
                            if (rule.ruleName.Equals(name, StringComparison.OrdinalIgnoreCase))
                            {
                                rule.isEnabled = state;
                                break;
                            }
                        }
                    }
                }
                else if (value == "outfit")
                {
                    foreach (var comp in UnityEngine.Object.FindObjectsByType<MonoBehaviour>(FindObjectsInactive.Exclude, FindObjectsSortMode.None))
                    {
                        if (comp == null) continue;
                        var type = comp.GetType();
                        if (type.Name == "MEClothes" && type.GetField("entries") != null)
                        {
                            var isScriptLoaderField = type.GetField("isScriptLoader");
                            bool isScriptLoader = isScriptLoaderField != null && (bool)isScriptLoaderField.GetValue(comp);
                            if (!isScriptLoader)
                            {
                                var entriesField = type.GetField("entries");
                                var entries = entriesField.GetValue(comp) as IEnumerable;
                                if (entries != null)
                                {
                                    int idx = 0;
                                    foreach (var entry in entries)
                                    {
                                        if (entry == null) { idx++; continue; }
                                        var nameField = entry.GetType().GetField("name");
                                        string outfitName = nameField?.GetValue(entry) as string;
                                        if (!string.IsNullOrEmpty(outfitName) && outfitName.Equals(name, StringComparison.OrdinalIgnoreCase))
                                        {
                                            var method = type.GetMethod("ActivateOutfit");
                                            if (method != null)
                                            {
                                                method.Invoke(comp, new object[] { idx });
                                            }
                                            break;
                                        }
                                        idx++;
                                    }
                                }
                            }
                        }
                    }
                }
                break;
        }
    }

    // =====================================================
    // ANIMATION — HasParameter guard (fixes GAP 3)
    // SetTrigger silently fails with a Unity warning every frame if the
    // parameter name doesn't exist.  HasParameter() prevents that noise.
    // =====================================================
    private void HandleAnimation(string animId)
    {
        if (string.IsNullOrEmpty(animId)) return;

        var sleepController = GetComponent<AvatarSleepController>();
        if (sleepController != null && sleepController.IsSleepLocked)
        {
            if (logMessages)
                Debug.Log($"[VivyWS] Animation '{animId}' blocked: Avatar is sleeping due to low circadian energy (< 40%).");
            return;
        }

        var resolver = GetComponent<VivyAnimationResolver>();
        if (resolver != null)
        {
            resolver.PlayAnimation(animId);
        }
        else if (animator != null && animator.IsValidAndPlaying())
        {
            // Fallback for backward compatibility if resolver is missing
            if (AnimatorHasParameter(animId, AnimatorControllerParameterType.Trigger))
            {
                animator.SetTrigger(animId);
            }
            else
            {
                if (logMessages)
                    Debug.LogWarning($"[VivyWS] Animator has no Trigger parameter '{animId}'. Skipping.");
            }
        }
    }

    // =====================================================
    // LOOK-AT — Routes to AvatarMouseTracking override (GAP 1)
    // x, y are normalised screen coordinates [0..1].
    // Converted to pixel space before passing to the override.
    // If mouseTracking is null or the override API is unavailable,
    // the call is silently skipped — existing mouse tracking is unaffected.
    // =====================================================
    private void HandleLookAt(float normX, float normY, float duration)
    {
        if (mouseTracking == null) return;

        float holdTime = duration > 0f ? duration : 2f; // default 2s if not specified

        mouseTracking.SetLookAtOverride(new Vector2(normX, normY), holdTime);
    }

    // =====================================================
    // STATUS — Drives Animator bools with HasParameter guard (GAP 2)
    // If the Animator controller does not have the named bool parameters,
    // the calls are silently skipped.  No animator controller edits required.
    // =====================================================
    private void HandleStatus(string status)
    {
        if (lipSync != null && status == "ready")
            lipSync.StopLipSync();

        if (animator == null || !animator.IsValidAndPlaying()) return;

        bool hasThinking = !string.IsNullOrEmpty(thinkingParam) &&
                           AnimatorHasParameter(thinkingParam, AnimatorControllerParameterType.Bool);
        bool hasSpeaking = !string.IsNullOrEmpty(speakingParam) &&
                           AnimatorHasParameter(speakingParam, AnimatorControllerParameterType.Bool);

        switch (status)
        {
            case "thinking":
                if (hasThinking) animator.SetBool(thinkingParam, true);
                if (hasSpeaking) animator.SetBool(speakingParam, false);
                break;

            case "speaking":
                if (hasThinking) animator.SetBool(thinkingParam, false);
                if (hasSpeaking) animator.SetBool(speakingParam, true);
                break;

            case "ready":
                if (hasThinking) animator.SetBool(thinkingParam, false);
                if (hasSpeaking) animator.SetBool(speakingParam, false);
                break;

            case "generating_tts":
            case "applying_rvc":
                // Processing states: keep thinking visible, not yet speaking
                if (hasThinking) animator.SetBool(thinkingParam, true);
                if (hasSpeaking) animator.SetBool(speakingParam, false);
                break;
        }
    }

    private void HandleLoadAvatar(string target)
    {
        var loader = FindFirstObjectByType<VRMLoader>();
        if (loader == null)
        {
            Debug.LogError("[VivyWS] VRMLoader not found in scene!");
            return;
        }

        if (string.IsNullOrEmpty(target) || target.ToLower() == "default" || target.ToLower() == "zome")
        {
            loader.ActivateDefaultModel();
        }
        else
        {
            loader.LoadVRM(target);
        }
    }

    private void HandleResize(int w, int h)
    {
        var streamer = GetComponent<VivyAvatarStreamer>();
        if (streamer != null)
        {
            streamer.ResizeStream(w, h);
        }
    }

    private void HandleCircadian(float energy, string phase)
    {
        var animController = GetComponent<AvatarAnimatorController>();
        if (animController != null)
        {
            animController.SetCircadianEnergy(energy, phase);
        }
        var sleepController = GetComponent<AvatarSleepController>();
        if (sleepController != null)
        {
            sleepController.UpdateCircadianEnergy(energy);
        }
    }

    private void HandleEmotionState(string rawJson)
    {
        try
        {
            var wrapper = JsonUtility.FromJson<EmotionStateWrapper>(rawJson);
            if (wrapper != null && wrapper.data != null)
            {
                var mgr = Vivy.AnimationFramework.EmotionLayers.EmotionLayerManager.Instance;
                if (mgr != null)
                {
                    mgr.ApplyEmotionState(wrapper.data);
                }
            }
        }
        catch (Exception ex)
        {
            Debug.LogWarning($"[VivyWS] Failed to parse EmotionState payload: {ex.Message}");
        }
    }

    [Serializable]
    private class EmotionStateWrapper
    {
        public string type = "";
        public Vivy.Contracts.EmotionState data = null;
    }

    // =====================================================
    // UTILITY — Safe parameter existence check
    // =====================================================
    private bool AnimatorHasParameter(string paramName, AnimatorControllerParameterType paramType)
    {
        if (animator == null || !animator.IsValidAndPlaying()) return false;
        foreach (var p in animator.parameters)
        {
            if (p.name == paramName && p.type == paramType)
                return true;
        }
        return false;
    }

    public bool IsConnected => _connected;

    // =====================================================
    // JSON DATA CLASS
    // Added: duration field for lookAt messages.
    // =====================================================
    [Serializable]
    private class VivyMessage
    {
        public string type     = "";
        public string value    = "";
        public string text     = "";
        public string name     = "";
        public float  weight   = 0f;
        public float  x        = 0f;
        public float  y        = 0f;
        public float  duration = 0f;
        public int    width    = 0;
        public int    height   = 0;
        public float  energy   = 1.0f;
        public string phase    = "";

        // Camera control fields
        public float  zoom     = 1f;
        public float  yaw      = 0f;
        public float  pitch    = 0f;
        public float  panX     = 0f;
        public float  panY     = 0f;

        // General interaction fields
        public string action   = "";
        public bool   state    = false;
    }

    [Serializable]
    private class GearOption
    {
        public string name;
        public string type; // "accessory" or "outfit"
        public bool state;
    }

    [Serializable]
    private class GearStatesMessage
    {
        public string type = "interaction";
        public string action = "gear_states";
        public List<GearOption> options;
    }

    private void SendGearStates()
    {
        var optionsList = new List<GearOption>();

        // 1. Gather accessories from AccessoiresHandler
        foreach (var handler in AccessoiresHandler.ActiveHandlers)
        {
            if (handler == null || handler.rules == null) continue;
            foreach (var rule in handler.rules)
            {
                if (rule == null || string.IsNullOrEmpty(rule.ruleName)) continue;
                optionsList.Add(new GearOption
                {
                    name = rule.ruleName,
                    type = "accessory",
                    state = rule.isEnabled
                });
            }
        }

        // 2. Gather outfits from MEClothes
        foreach (var comp in UnityEngine.Object.FindObjectsByType<MonoBehaviour>(FindObjectsInactive.Exclude, FindObjectsSortMode.None))
        {
            if (comp == null) continue;
            var type = comp.GetType();
            if (type.Name == "MEClothes" && type.GetField("entries") != null)
            {
                var isScriptLoaderField = type.GetField("isScriptLoader");
                bool isScriptLoader = isScriptLoaderField != null && (bool)isScriptLoaderField.GetValue(comp);
                if (!isScriptLoader)
                {
                    var entriesField = type.GetField("entries");
                    var entries = entriesField.GetValue(comp) as IEnumerable;
                    if (entries != null)
                    {
                        foreach (var entry in entries)
                        {
                            if (entry == null) continue;
                            var nameField = entry.GetType().GetField("name");
                            string outfitName = nameField?.GetValue(entry) as string;
                            if (!string.IsNullOrEmpty(outfitName))
                            {
                                var gameObjectsField = entry.GetType().GetField("gameObjects");
                                var gameObjects = gameObjectsField?.GetValue(entry) as GameObject[];
                                bool isCurrentlyOn = false;
                                if (gameObjects != null)
                                {
                                    foreach (var go in gameObjects)
                                    {
                                        if (go != null && go.activeSelf)
                                        {
                                            isCurrentlyOn = true;
                                            break;
                                        }
                                    }
                                }

                                optionsList.Add(new GearOption
                                {
                                    name = outfitName,
                                    type = "outfit",
                                    state = isCurrentlyOn
                                });
                            }
                        }
                    }
                }
            }
        }

        var msgObj = new GearStatesMessage { options = optionsList };
        string json = JsonUtility.ToJson(msgObj);
        SendRawPayload(json);
    }
    private void HandleSyncPose(string rawJson)
    {
        try
        {
            SyncPoseData poseData = JsonUtility.FromJson<SyncPoseData>(rawJson);
            if (poseData == null || poseData.bones == null || animator == null || !animator.IsValidAndPlaying()) return;
            
            _latestSyncPose = poseData;
        }
        catch (Exception ex)
        {
            Debug.LogWarning($"[VivyWS] Failed to parse sync_pose: {ex.Message}");
        }
    }
}

[Serializable]
public class SyncPoseData
{
    public string type;
    public BonePose[] bones;
}

[Serializable]
public class BonePose
{
    public string name;
    public float x;
    public float y;
    public float z;
    public float w;
}
