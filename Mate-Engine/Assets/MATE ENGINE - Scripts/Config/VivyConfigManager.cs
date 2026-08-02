using System;
using System.IO;
using UnityEngine;

namespace Vivy.Config
{
    /// <summary>
    /// Vivy Centralized Unity Configuration Manager (v1.0.0).
    /// Single source of truth for Unity-side component configuration & feature flags.
    /// Reads from vivy_unity_config.json at startup with hot-reload capability.
    /// </summary>
    [DefaultExecutionOrder(-200)]
    public class VivyConfigManager : MonoBehaviour
    {
        private static VivyConfigManager _instance;
        public static VivyConfigManager Instance => _instance;

        [Header("Config Settings")]
        public string configFileName = "vivy_unity_config.json";
        public bool enableHotReload = true;
        public float checkInterval = 2.0f;

        [Header("Loaded Configuration Data")]
        public UnityConfigData configData = new UnityConfigData();

        private string _fullConfigPath;
        private DateTime _lastMTime;
        private float _nextCheckTime;

        void Awake()
        {
            if (_instance != null && _instance != this)
            {
                Destroy(gameObject);
                return;
            }
            _instance = this;
            if (transform.parent != null)
                DontDestroyOnLoad(transform.root.gameObject);
            else
                DontDestroyOnLoad(gameObject);

            ResolveConfigPath();
            LoadConfig();
        }

        void Update()
        {
            if (!enableHotReload) return;

            if (Time.unscaledTime >= _nextCheckTime)
            {
                _nextCheckTime = Time.unscaledTime + checkInterval;
                CheckHotReload();
            }
        }

        private void ResolveConfigPath()
        {
            // First check project root, then persistentDataPath
            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, "..", ".."));
            string pathInRoot = Path.Combine(projectRoot, configFileName);

            if (File.Exists(pathInRoot))
            {
                _fullConfigPath = pathInRoot;
            }
            else
            {
                _fullConfigPath = Path.Combine(Application.persistentDataPath, configFileName);
            }
        }

        public void LoadConfig()
        {
            try
            {
                if (File.Exists(_fullConfigPath))
                {
                    string json = File.ReadAllText(_fullConfigPath);
                    configData = JsonUtility.FromJson<UnityConfigData>(json) ?? new UnityConfigData();
                    _lastMTime = File.GetLastWriteTime(_fullConfigPath);
                    Debug.Log($"[VivyConfig] Successfully loaded configuration from {_fullConfigPath}");
                }
                else
                {
                    Debug.LogWarning($"[VivyConfig] Config file not found at {_fullConfigPath}. Creating default file.");
                    SaveDefaultConfig();
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"[VivyConfig] Error loading configuration: {ex.Message}");
            }
        }

        private void CheckHotReload()
        {
            try
            {
                if (File.Exists(_fullConfigPath))
                {
                    DateTime mtime = File.GetLastWriteTime(_fullConfigPath);
                    if (mtime > _lastMTime)
                    {
                        Debug.Log("[VivyConfig] Hot-reload triggered by file modification.");
                        LoadConfig();
                    }
                }
            }
            catch { }
        }

        private void SaveDefaultConfig()
        {
            try
            {
                string json = JsonUtility.ToJson(configData, true);
                string dir = Path.GetDirectoryName(_fullConfigPath);
                if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
                File.WriteAllText(_fullConfigPath, json);
            }
            catch (Exception ex)
            {
                Debug.LogError($"[VivyConfig] Error saving default config: {ex.Message}");
            }
        }

        public bool IsFeatureEnabled(string flagName, bool defaultValue = true)
        {
            if (configData == null || configData.feature_flags == null) return defaultValue;
            return flagName switch
            {
                "procedural_breathing"  => configData.feature_flags.procedural_breathing,
                "procedural_blinking"   => configData.feature_flags.procedural_blinking,
                "procedural_saccades"   => configData.feature_flags.procedural_saccades,
                "procedural_weight_shift" => configData.feature_flags.procedural_weight_shift,
                "emotion_layers"        => configData.feature_flags.emotion_layers,
                "behavior_tree"         => configData.feature_flags.behavior_tree,
                "structured_logging"    => configData.feature_flags.structured_logging,
                "error_recovery"        => configData.feature_flags.error_recovery,
                _ => defaultValue
            };
        }
    }

    [Serializable]
    public class UnityConfigData
    {
        public ConnectionConfig connection = new ConnectionConfig();
        public StatusParamsConfig status_parameters = new StatusParamsConfig();
        public StreamerConfig streamer = new StreamerConfig();
        public EmotionMapperConfig emotion_mapper = new EmotionMapperConfig();
        public LipSyncConfig lip_sync = new LipSyncConfig();
        public MouseTrackingConfig mouse_tracking = new MouseTrackingConfig();
        public FeatureFlagsConfig feature_flags = new FeatureFlagsConfig();
    }

    [Serializable]
    public class ConnectionConfig
    {
        public string server_uri = "ws://127.0.0.1:8765";
        public float reconnect_delay = 3.0f;
        public bool auto_connect = true;
        public bool log_messages = true;
    }

    [Serializable]
    public class StatusParamsConfig
    {
        public string thinking_param = "isThinking";
        public string speaking_param = "isSpeaking";
    }

    [Serializable]
    public class StreamerConfig
    {
        public bool enable_streaming = true;
        public int width = 640;
        public int height = 640;
        public float render_scale = 1.0f;
        public float fps = 60.0f;
        public int jpeg_quality = 90;
        public float field_of_view = 35.0f;
    }

    [Serializable]
    public class EmotionMapperConfig
    {
        public float transition_speed = 3.0f;
        public float max_expression_intensity = 0.85f;
        public bool log_emotion_changes = true;
    }

    [Serializable]
    public class LipSyncConfig
    {
        public float phoneme_duration = 0.07f;
        public float viseme_intensity = 0.75f;
        public float smooth_speed = 12.0f;
    }

    [Serializable]
    public class MouseTrackingConfig
    {
        public bool enable_mouse_tracking = true;
        public float head_yaw_limit = 45.0f;
        public float head_pitch_limit = 30.0f;
        public float head_smoothness = 10.0f;
        public float spine_smoothness = 25.0f;
        public float eye_yaw_limit = 12.0f;
        public float eye_pitch_limit = 12.0f;
    }

    [Serializable]
    public class FeatureFlagsConfig
    {
        public bool procedural_breathing = true;
        public bool procedural_blinking = true;
        public bool procedural_saccades = true;
        public bool procedural_weight_shift = true;
        public bool emotion_layers = true;
        public bool behavior_tree = true;
        public bool structured_logging = true;
        public bool error_recovery = true;
    }
}
