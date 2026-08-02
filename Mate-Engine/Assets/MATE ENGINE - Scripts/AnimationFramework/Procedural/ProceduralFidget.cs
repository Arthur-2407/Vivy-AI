using System.Collections;
using UnityEngine;

namespace Vivy.AnimationFramework.Procedural
{
    /// <summary>
    /// Procedural Idle Fidget Layer (v1.0.0).
    /// Per Phase 4 of the Master Hyperprompt.
    /// Modulates hand/finger bone rotations during idle states.
    /// </summary>
    [RequireComponent(typeof(Animator))]
    public class ProceduralFidget : MonoBehaviour, IProceduralMotion
    {
        public bool isEnabled = true;
        [Range(0f, 1f)] public float weight = 1.0f;
        public float minFidgetInterval = 4.0f;
        public float maxFidgetInterval = 10.0f;

        public bool IsEnabled { get => isEnabled; set => isEnabled = value; }
        public float Weight { get => weight; set => weight = value; }

        private Animator _animator;
        private Transform _leftHandBone;
        private Transform _rightHandBone;
        private float _nextFidgetTime;
        private bool _isFidgeting;

        void Start()
        {
            _animator = GetComponent<Animator>();
            if (_animator != null && _animator.isHuman)
            {
                _leftHandBone = _animator.GetBoneTransform(HumanBodyBones.LeftHand);
                _rightHandBone = _animator.GetBoneTransform(HumanBodyBones.RightHand);
            }
            ScheduleNextFidget();
        }

        void Update()
        {
            if (!isEnabled || weight <= 0.001f) return;
            if (!_isFidgeting && Time.time >= _nextFidgetTime)
            {
                StartCoroutine(FidgetCoroutine());
            }
        }

        public void UpdateMotion(float deltaTime) { }

        private void ScheduleNextFidget()
        {
            _nextFidgetTime = Time.time + Random.Range(minFidgetInterval, maxFidgetInterval);
        }

        private IEnumerator FidgetCoroutine()
        {
            _isFidgeting = true;
            float duration = Random.Range(0.5f, 1.2f);
            float elapsed = 0f;
            Transform targetHand = (Random.value < 0.5f) ? _leftHandBone : _rightHandBone;

            if (targetHand != null)
            {
                Quaternion startRot = targetHand.localRotation;
                Quaternion targetRot = startRot * Quaternion.Euler(Random.Range(-5f, 5f), Random.Range(-5f, 5f), Random.Range(-5f, 5f));

                while (elapsed < duration)
                {
                    elapsed += Time.deltaTime;
                    float t = Mathf.Sin((elapsed / duration) * Mathf.PI);
                    targetHand.localRotation = Quaternion.Slerp(startRot, targetRot, t * weight);
                    yield return null;
                }
            }

            _isFidgeting = false;
            ScheduleNextFidget();
        }
    }
}
