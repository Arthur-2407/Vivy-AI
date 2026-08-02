using UnityEngine;

namespace Vivy.AnimationFramework.Procedural
{
    /// <summary>
    /// Procedural Breathing Layer (v1.0.0).
    /// Per Phase 4 of the Master Hyperprompt.
    /// Modulates spine/chest rotation smoothly with configurable rate and depth.
    /// </summary>
    [RequireComponent(typeof(Animator))]
    public class ProceduralBreathing : MonoBehaviour, IProceduralMotion
    {
        [Header("Breathing Settings")]
        public bool isEnabled = true;
        [Range(0f, 1f)] public float weight = 1.0f;
        public float breathsPerMinute = 16.0f;
        public float chestRotationDegrees = 1.5f;

        public bool IsEnabled { get => isEnabled; set => isEnabled = value; }
        public float Weight { get => weight; set => weight = value; }

        private Animator _animator;
        private Transform _chestBone;
        private float _breathTimer;

        void Start()
        {
            _animator = GetComponent<Animator>();
            if (_animator != null && _animator.isHuman)
            {
                _chestBone = _animator.GetBoneTransform(HumanBodyBones.Chest) ??
                             _animator.GetBoneTransform(HumanBodyBones.Spine);
            }
        }

        void LateUpdate()
        {
            if (!isEnabled || weight <= 0.001f || _chestBone == null) return;
            UpdateMotion(Time.deltaTime);
        }

        public void UpdateMotion(float deltaTime)
        {
            _breathTimer += deltaTime * (breathsPerMinute / 60.0f) * Mathf.PI * 2.0f;
            float sineWave = Mathf.Sin(_breathTimer);

            // Apply slight pitch rotation to chest bone
            float rotX = sineWave * chestRotationDegrees * weight;
            _chestBone.localRotation *= Quaternion.Euler(rotX, 0f, 0f);
        }

        public void ModulateByEnergy(float energy)
        {
            energy = Mathf.Clamp01(energy);
            breathsPerMinute = Mathf.Lerp(12.0f, 24.0f, energy);
            chestRotationDegrees = Mathf.Lerp(1.0f, 2.5f, energy);
        }
    }
}
