using UnityEngine;
using System.Collections;
using System.Collections.Generic;

namespace Vivy.AnimationFramework
{
    /// <summary>
    /// Vivy AI - Procedural Deep Breathing Animation System
    /// 
    /// Adds procedural breathing motion to humanoid bones during LateUpdate, 
    /// preserving all existing Animator states, IK, and gestures.
    /// Reads emotion state dynamically without modifying it.
    /// </summary>
    public class DeepBreathingAnimation : MonoBehaviour
    {
        [Header("System Status")]
        public bool isInitialized = false;
        public string currentPhase = "Inhale";
        
        [Header("Configuration")]
        public bool enableProceduralMode = true;
        public bool enableScaling = true;
        public bool enableRotation = true;
        public bool enableTranslation = true;
        
        [Header("Timing (Base Cycle)")]
        [Range(1f, 10f)] public float inhaleDuration = 4.0f;
        [Range(1f, 10f)] public float exhaleDuration = 4.0f;
        [Range(0f, 3f)] public float holdAfterInhale = 1.0f;
        [Range(0f, 3f)] public float holdAfterExhale = 1.0f;
        
        [Header("Movement Limits")]
        [Range(1.0f, 1.1f)] public float chestScaleMax = 1.03f;
        [Range(0f, 10f)] public float upperChestRotationMax = 3.0f;
        [Range(0f, 10f)] public float spineRotationMax = 1.5f;
        [Range(0f, 0.05f)] public float shoulderElevationMax = 0.015f;
        [Range(0f, 5f)] public float neckAdjustmentMax = 1.0f;

        [Header("Debug")]
        public bool debugMode = false;
        
        // ----------------------------------------------------
        // Internal State
        // ----------------------------------------------------
        private Animator _animator;
        private VivyEmotionMapper _emotionMapper;
        
        // Bone References
        private Transform _chest;
        private Transform _upperChest;
        private Transform _spine;
        private Transform _leftShoulder;
        private Transform _rightShoulder;
        private Transform _neck;
        
        // Base States to prevent compounding (Mesh Explosion Fix)
        private Vector3 _origChestScale = Vector3.one;
        private Vector3 _origLeftShoulderPos;
        private Vector3 _origRightShoulderPos;
        private Quaternion _origUpperChestRot;
        private Quaternion _origSpineRot;
        private Quaternion _origNeckRot;
        
        // Cycle State
        private float _cycleTimer = 0f;
        private float _breatheValue = 0f; // 0.0 (empty) to 1.0 (full)
        private float _emotionSpeedMultiplier = 1.0f;
        private float _emotionIntensityMultiplier = 1.0f;
        
        void Start()
        {
            InitializeSystem();
        }

        private void InitializeSystem()
        {
            _animator = GetComponent<Animator>();
            if (_animator == null)
            {
                if (debugMode) Debug.LogWarning("[DeepBreathing] Animator not found on this GameObject. Attempting to find in children.");
                _animator = GetComponentInChildren<Animator>();
            }

            if (_animator == null || !_animator.isHuman)
            {
                if (debugMode) Debug.LogError("[DeepBreathing] No Humanoid Animator found. Procedural breathing disabled.");
                enableProceduralMode = false;
                return;
            }

            _emotionMapper = GetComponent<VivyEmotionMapper>();
            if (_emotionMapper == null) _emotionMapper = GetComponentInChildren<VivyEmotionMapper>();

            // Auto-detect bones
            _chest = _animator.GetBoneTransform(HumanBodyBones.Chest);
            _upperChest = _animator.GetBoneTransform(HumanBodyBones.UpperChest);
            _spine = _animator.GetBoneTransform(HumanBodyBones.Spine);
            _leftShoulder = _animator.GetBoneTransform(HumanBodyBones.LeftShoulder);
            _rightShoulder = _animator.GetBoneTransform(HumanBodyBones.RightShoulder);
            _neck = _animator.GetBoneTransform(HumanBodyBones.Neck);

            // Failsafe Logic: Ensure we have a primary breathing torso bone
            if (_chest == null)
            {
                if (debugMode) Debug.Log("[DeepBreathing] Chest bone missing. Falling back to UpperChest.");
                _chest = _upperChest;
            }
            if (_chest == null)
            {
                if (debugMode) Debug.Log("[DeepBreathing] UpperChest missing. Falling back to Spine.");
                _chest = _spine;
            }
            if (_chest == null)
            {
                if (debugMode) Debug.LogError("[DeepBreathing] No usable torso bones found (Chest/UpperChest/Spine). Disabling system.");
                enableProceduralMode = false;
                return;
            }

            // Capture original scale to prevent LateUpdate compounding
            _origChestScale = _chest.localScale;

            isInitialized = true;
            if (debugMode)
            {
                Debug.Log($"[DeepBreathing] Initialized successfully. Primary Torso: {_chest.name}");
            }
        }

        void LateUpdate()
        {
            if (!isInitialized || !enableProceduralMode) return;

            UpdateEmotionMultipliers();
            UpdateBreathingCycle();
            ApplyProceduralMotion();
        }

        private void UpdateEmotionMultipliers()
        {
            if (_emotionMapper == null) return;
            
            string emotion = _emotionMapper.currentEmotion.ToLower();
            
            // Adjust speed and intensity based on emotion (read-only)
            switch (emotion)
            {
                case "joy":
                case "happy":
                    _emotionSpeedMultiplier = 1.1f;
                    _emotionIntensityMultiplier = 1.1f;
                    break;
                case "surprise":
                case "excited":
                    _emotionSpeedMultiplier = 1.4f;
                    _emotionIntensityMultiplier = 1.2f;
                    break;
                case "fear":
                case "anxious":
                case "angry":
                case "anger":
                    _emotionSpeedMultiplier = 1.6f;
                    _emotionIntensityMultiplier = 0.8f; // shallower breathing
                    break;
                case "sadness":
                case "sorrow":
                case "sad":
                    _emotionSpeedMultiplier = 0.8f;
                    _emotionIntensityMultiplier = 1.1f; // deeper sighs
                    break;
                case "sleepy":
                    _emotionSpeedMultiplier = 0.6f;
                    _emotionIntensityMultiplier = 1.2f;
                    break;
                case "neutral":
                default:
                    _emotionSpeedMultiplier = 1.0f;
                    _emotionIntensityMultiplier = 1.0f;
                    break;
            }
        }

        private void UpdateBreathingCycle()
        {
            float effInhale = inhaleDuration / _emotionSpeedMultiplier;
            float effExhale = exhaleDuration / _emotionSpeedMultiplier;
            float effHoldIn = holdAfterInhale / _emotionSpeedMultiplier;
            float effHoldEx = holdAfterExhale / _emotionSpeedMultiplier;
            
            float totalCycleTime = effInhale + effHoldIn + effExhale + effHoldEx;
            
            _cycleTimer += Time.deltaTime;
            if (_cycleTimer >= totalCycleTime)
            {
                _cycleTimer -= totalCycleTime; // loop
            }

            if (_cycleTimer < effInhale)
            {
                currentPhase = "Inhale";
                // Ease in/out using smoothstep interpolation
                float t = _cycleTimer / effInhale;
                _breatheValue = Mathf.SmoothStep(0f, 1f, t);
            }
            else if (_cycleTimer < effInhale + effHoldIn)
            {
                currentPhase = "Hold (Full)";
                _breatheValue = 1f;
            }
            else if (_cycleTimer < effInhale + effHoldIn + effExhale)
            {
                currentPhase = "Exhale";
                float t = (_cycleTimer - effInhale - effHoldIn) / effExhale;
                _breatheValue = Mathf.SmoothStep(1f, 0f, t);
            }
            else
            {
                currentPhase = "Hold (Empty)";
                _breatheValue = 0f;
            }
        }

        private void ApplyProceduralMotion()
        {
            float intensity = _breatheValue * _emotionIntensityMultiplier;

            // 1. SCALING (Chest Expansion)
            if (enableScaling && _chest != null)
            {
                // CRITICAL FIX: Multiply the ORIGINAL scale by the modifier.
                // Do NOT multiply the current scale, as the Animator rarely updates localScale,
                // which causes multiplicative compounding every frame leading to mesh explosions!
                float scaleMod = Mathf.Lerp(1.0f, chestScaleMax, intensity);
                _chest.localScale = new Vector3(
                    _origChestScale.x * scaleMod, 
                    _origChestScale.y * scaleMod, 
                    _origChestScale.z * scaleMod
                );
            }

            // 2. ROTATION (Upper Torso backward tilt)
            // Humanoid Animators overwrite rotation every frame, so it is safe to apply relative rotations here without compounding.
            if (enableRotation)
            {
                if (_upperChest != null)
                {
                    float angle = Mathf.Lerp(0f, -upperChestRotationMax, intensity);
                    _upperChest.localRotation *= Quaternion.AngleAxis(angle, Vector3.right);
                }
                else if (_spine != null)
                {
                    float angle = Mathf.Lerp(0f, -spineRotationMax, intensity);
                    _spine.localRotation *= Quaternion.AngleAxis(angle, Vector3.right);
                }

                if (_neck != null)
                {
                    float neckAngle = Mathf.Lerp(0f, neckAdjustmentMax, intensity);
                    _neck.localRotation *= Quaternion.AngleAxis(neckAngle, Vector3.right);
                }
            }

            // 3. TRANSLATION (Shoulders rising)
            // Similarly, translation on shoulders is generally overwritten by the Animator's muscle constraints.
            if (enableTranslation)
            {
                if (_leftShoulder != null)
                {
                    Vector3 localUp = _leftShoulder.InverseTransformDirection(Vector3.up);
                    _leftShoulder.localPosition += localUp * Mathf.Lerp(0f, shoulderElevationMax, intensity);
                }
                
                if (_rightShoulder != null)
                {
                    Vector3 localUp = _rightShoulder.InverseTransformDirection(Vector3.up);
                    _rightShoulder.localPosition += localUp * Mathf.Lerp(0f, shoulderElevationMax, intensity);
                }
            }
        }
    }
}
