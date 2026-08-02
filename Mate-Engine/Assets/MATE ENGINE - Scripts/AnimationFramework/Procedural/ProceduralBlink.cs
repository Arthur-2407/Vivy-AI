using System.Collections;
using UnityEngine;

namespace Vivy.AnimationFramework.Procedural
{
    /// <summary>
    /// Procedural Blinking Layer (v1.0.0).
    /// Per Phase 4 of the Master Hyperprompt.
    /// Drives UniversalBlendshapes Blink value with natural interval distribution.
    /// </summary>
    public class ProceduralBlink : MonoBehaviour, IProceduralMotion
    {
        public bool isEnabled = true;
        [Range(0f, 1f)] public float weight = 1.0f;
        public float minBlinkInterval = 2.5f;
        public float maxBlinkInterval = 6.0f;
        public float blinkDuration = 0.12f;

        public bool IsEnabled { get => isEnabled; set => isEnabled = value; }
        public float Weight { get => weight; set => weight = value; }

        private UniversalBlendshapes _blendshapes;
        private float _nextBlinkTime;
        private bool _isBlinking;

        void Start()
        {
            _blendshapes = GetComponent<UniversalBlendshapes>() ?? GetComponentInParent<UniversalBlendshapes>();
            ScheduleNextBlink();
        }

        void Update()
        {
            if (!isEnabled || weight <= 0.001f || _blendshapes == null) return;

            if (!_isBlinking && Time.time >= _nextBlinkTime)
            {
                StartCoroutine(BlinkCoroutine());
            }
        }

        public void UpdateMotion(float deltaTime) { }

        private void ScheduleNextBlink()
        {
            _nextBlinkTime = Time.time + Random.Range(minBlinkInterval, maxBlinkInterval);
        }

        private IEnumerator BlinkCoroutine()
        {
            _isBlinking = true;
            float elapsed = 0f;
            float halfDuration = blinkDuration * 0.5f;

            // Closing eyes
            while (elapsed < halfDuration)
            {
                elapsed += Time.deltaTime;
                _blendshapes.Blink = (elapsed / halfDuration) * weight;
                yield return null;
            }

            // Opening eyes
            elapsed = 0f;
            while (elapsed < halfDuration)
            {
                elapsed += Time.deltaTime;
                _blendshapes.Blink = (1.0f - (elapsed / halfDuration)) * weight;
                yield return null;
            }

            _blendshapes.Blink = 0f;
            _isBlinking = false;
            ScheduleNextBlink();
        }
    }
}
