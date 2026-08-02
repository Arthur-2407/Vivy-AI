using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using Vivy.Logging;

namespace Vivy.AnimationFramework
{
    /// <summary>
    /// Programmatic Animator Layer Manager (v1.0.0).
    /// Manages layer weights smoothly with timed interpolation.
    /// </summary>
    [RequireComponent(typeof(Animator))]
    public class LayerManager : MonoBehaviour, ILayerManager
    {
        private Animator _animator;
        private Dictionary<int, Coroutine> _activeFades = new Dictionary<int, Coroutine>();

        void Awake()
        {
            _animator = GetComponent<Animator>();
        }

        public void SetLayerWeight(int layerIndex, float weight, float duration = 0)
        {
            if (_animator == null || layerIndex < 0 || layerIndex >= _animator.layerCount) return;

            weight = Mathf.Clamp01(weight);

            if (_activeFades.TryGetValue(layerIndex, out var coroutine) && coroutine != null)
            {
                StopCoroutine(coroutine);
            }

            if (duration <= 0f)
            {
                _animator.SetLayerWeight(layerIndex, weight);
            }
            else
            {
                _activeFades[layerIndex] = StartCoroutine(FadeLayerCoroutine(layerIndex, weight, duration));
            }
        }

        public void SetLayerWeight(string layerName, float weight, float duration = 0)
        {
            int idx = GetLayerIndex(layerName);
            if (idx >= 0)
            {
                SetLayerWeight(idx, weight, duration);
            }
        }

        public float GetLayerWeight(string layerName)
        {
            int idx = GetLayerIndex(layerName);
            return (idx >= 0 && _animator != null) ? _animator.GetLayerWeight(idx) : 0f;
        }

        public int GetLayerIndex(string layerName)
        {
            if (_animator == null || string.IsNullOrEmpty(layerName)) return -1;
            return _animator.GetLayerIndex(layerName);
        }

        private IEnumerator FadeLayerCoroutine(int layerIndex, float targetWeight, float duration)
        {
            float elapsed = 0f;
            float startWeight = _animator.GetLayerWeight(layerIndex);

            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float current = Mathf.Lerp(startWeight, targetWeight, elapsed / duration);
                _animator.SetLayerWeight(layerIndex, current);
                yield return null;
            }

            _animator.SetLayerWeight(layerIndex, targetWeight);
            _activeFades.Remove(layerIndex);
        }
    }
}
