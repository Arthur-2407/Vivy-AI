using UnityEngine;

namespace Vivy.AnimationFramework.Procedural
{
    /// <summary>
    /// Procedural Weight Shift Layer (v1.0.0).
    /// Per Phase 4 of the Master Hyperprompt.
    /// Modulates spine/hips roll and pitch to simulate balance correction during idle.
    /// </summary>
    [RequireComponent(typeof(Animator))]
    public class ProceduralWeightShift : MonoBehaviour, IProceduralMotion
    {
        public bool isEnabled = true;
        [Range(0f, 1f)] public float weight = 1.0f;
        public float shiftCycleSeconds = 8.0f;
        public float swayDegrees = 1.2f;

        public bool IsEnabled { get => isEnabled; set => isEnabled = value; }
        public float Weight { get => weight; set => weight = value; }

        private Animator _animator;
        private Transform _spineBone;
        private float _timer;

        void Start()
        {
            _animator = GetComponent<Animator>();
            if (_animator != null && _animator.isHuman)
            {
                _spineBone = _animator.GetBoneTransform(HumanBodyBones.Spine);
            }
        }

        void LateUpdate()
        {
            if (!isEnabled || weight <= 0.001f || _spineBone == null) return;
            UpdateMotion(Time.deltaTime);
        }

        public void UpdateMotion(float deltaTime)
        {
            _timer += deltaTime * (Mathf.PI * 2.0f / shiftCycleSeconds);
            float sineZ = Mathf.Sin(_timer);
            float cosineX = Mathf.Cos(_timer * 0.5f);

            float rotZ = sineZ * swayDegrees * weight;
            float rotX = cosineX * swayDegrees * 0.5f * weight;

            _spineBone.localRotation *= Quaternion.Euler(rotX, 0f, rotZ);
        }
    }
}
