using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace Vivy.AnimationFramework
{
    /// <summary>
    /// Blend Parameter Manager (v1.0.0).
    /// Handles smooth parameter interpolation for Animator blend trees.
    /// </summary>
    [RequireComponent(typeof(Animator))]
    public class BlendManager : MonoBehaviour, IBlendManager
    {
        private Animator _animator;
        private Dictionary<string, Coroutine> _activeSmooths = new Dictionary<string, Coroutine>();

        void Awake()
        {
            _animator = GetComponent<Animator>();
        }

        public void SetBlendParameter(string paramName, float value, float smoothDuration = 0)
        {
            if (_animator == null || string.IsNullOrEmpty(paramName)) return;

            if (_activeSmooths.TryGetValue(paramName, out var coroutine) && coroutine != null)
            {
                StopCoroutine(coroutine);
            }

            if (smoothDuration <= 0f)
            {
                _animator.SetFloat(paramName, value);
            }
            else
            {
                _activeSmooths[paramName] = StartCoroutine(SmoothParameterCoroutine(paramName, value, smoothDuration));
            }
        }

        public float GetBlendParameter(string paramName)
        {
            if (_animator == null || string.IsNullOrEmpty(paramName)) return 0f;
            return _animator.GetFloat(paramName);
        }

        private IEnumerator SmoothParameterCoroutine(string paramName, float targetValue, float duration)
        {
            float elapsed = 0f;
            float startVal = _animator.GetFloat(paramName);

            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float current = Mathf.Lerp(startVal, targetValue, elapsed / duration);
                _animator.SetFloat(paramName, current);
                yield return null;
            }

            _animator.SetFloat(paramName, targetValue);
            _activeSmooths.Remove(paramName);
        }
    }
}
