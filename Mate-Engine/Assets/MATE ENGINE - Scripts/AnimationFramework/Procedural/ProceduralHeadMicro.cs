using UnityEngine;

namespace Vivy.AnimationFramework.Procedural
{
    /// <summary>
    /// Procedural Head Micro Motion Layer (v1.0.0).
    /// Per Phase 4 of the Master Hyperprompt.
    /// Modulates head tilt/yaw subtly during idle and active listening.
    /// </summary>
    [RequireComponent(typeof(Animator))]
    public class ProceduralHeadMicro : MonoBehaviour, IProceduralMotion
    {
        public bool isEnabled = true;
        [Range(0f, 1f)] public float weight = 1.0f;
        public float microSpeed = 1.5f;
        public float maxTiltDegrees = 1.0f;

        public bool IsEnabled { get => isEnabled; set => isEnabled = value; }
        public float Weight { get => weight; set => weight = value; }

        private Animator _animator;
        private Transform _headBone;
        private float _perlinNoiseSeed;

        void Start()
        {
            _animator = GetComponent<Animator>();
            if (_animator != null && _animator.isHuman)
            {
                _headBone = _animator.GetBoneTransform(HumanBodyBones.Head);
            }
            _perlinNoiseSeed = Random.Range(0f, 100f);
        }

        void LateUpdate()
        {
            if (!isEnabled || weight <= 0.001f || _headBone == null) return;
            UpdateMotion(Time.deltaTime);
        }

        public void UpdateMotion(float deltaTime)
        {
            float time = Time.time * microSpeed + _perlinNoiseSeed;
            float pitch = (Mathf.PerlinNoise(time, 0f) - 0.5f) * 2.0f * maxTiltDegrees * weight;
            float yaw   = (Mathf.PerlinNoise(0f, time) - 0.5f) * 2.0f * maxTiltDegrees * weight;
            float roll  = (Mathf.PerlinNoise(time, time) - 0.5f) * 2.0f * (maxTiltDegrees * 0.5f) * weight;

            _headBone.localRotation *= Quaternion.Euler(pitch, yaw, roll);
        }
    }
}
