using UnityEngine;
using Vivy.Logging;

namespace Vivy.AnimationFramework
{
    /// <summary>
    /// Smooth Transition Manager (v1.0.0).
    /// Handles interruptible, blend-aware state transitions in Unity Animator.
    /// </summary>
    [RequireComponent(typeof(Animator))]
    public class TransitionManager : MonoBehaviour, ITransitionManager
    {
        private Animator _animator;

        void Awake()
        {
            _animator = GetComponent<Animator>();
        }

        public void TransitionToState(string stateName, float crossfadeDuration = 0.25f, int layerIndex = 0)
        {
            if (_animator == null || string.IsNullOrEmpty(stateName)) return;

            VivyLogger.Info("TransitionManager", $"Crossfading to state '{stateName}' on layer {layerIndex} over {crossfadeDuration}s");
            _animator.CrossFade(stateName, crossfadeDuration, layerIndex);
        }

        public bool IsTransitioning(int layerIndex = 0)
        {
            if (_animator == null || layerIndex < 0 || layerIndex >= _animator.layerCount) return false;
            return _animator.IsInTransition(layerIndex);
        }
    }
}
