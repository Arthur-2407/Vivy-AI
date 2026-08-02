using System;
using System.Collections.Generic;
using UnityEngine;
using Vivy.Contracts;
using Vivy.Logging;
using Vivy.Recovery;

namespace Vivy.AnimationFramework
{
    /// <summary>
    /// Central Runtime Animation Manager (v1.0.0).
    /// Wraps Unity Animator operations, evaluates AnimationRequests,
    /// checks parameters safely, and manages priority queuing.
    /// </summary>
    [RequireComponent(typeof(Animator))]
    public class RuntimeAnimationManager : MonoBehaviour, IRuntimeAnimationManager
    {
        public static RuntimeAnimationManager Instance { get; private set; }

        public Animator targetAnimator;
        public AnimationRegistry registry;

        private Queue<AnimationRequest> _requestQueue = new Queue<AnimationRequest>();
        private AnimationRequest _currentActiveRequest;

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;

            if (targetAnimator == null) targetAnimator = GetComponent<Animator>();
            if (registry == null) registry = AnimationRegistry.Instance ?? GetComponent<AnimationRegistry>();
        }

        public AnimationResponse RequestAnimation(AnimationRequest request)
        {
            if (request == null)
            {
                return new AnimationResponse { status = "failed", error_message = "Null request" };
            }

            return VivyErrorRecovery.ExecuteSafe("AnimationManager", () =>
            {
                VivyLogger.Info("AnimationManager", $"Received AnimationRequest for clip/trigger '{request.clip_or_procedural_id}' (Priority: {request.priority})");

                string triggerToUse = request.clip_or_procedural_id;
                if (string.IsNullOrEmpty(triggerToUse) && registry != null)
                {
                    triggerToUse = registry.FallbackTrigger;
                }

                if (HasParameter(triggerToUse, AnimatorControllerParameterType.Trigger))
                {
                    targetAnimator.SetTrigger(triggerToUse);
                    _currentActiveRequest = request;
                    return new AnimationResponse
                    {
                        request_id = request.request_id,
                        status = "playing",
                        resolved_clips = new List<string> { triggerToUse },
                        estimated_duration = request.transition_duration
                    };
                }
                else
                {
                    VivyLogger.Warn("AnimationManager", $"Animator missing trigger '{triggerToUse}'. Falling back.");
                    string fallback = registry != null ? registry.FallbackTrigger : "Idle0";
                    if (HasParameter(fallback, AnimatorControllerParameterType.Trigger))
                    {
                        targetAnimator.SetTrigger(fallback);
                    }
                    return new AnimationResponse
                    {
                        request_id = request.request_id,
                        status = "playing_fallback",
                        resolved_clips = new List<string> { fallback }
                    };
                }
            }, new AnimationResponse { status = "failed", error_message = "Recovery fallback" });
        }

        public void PlayTrigger(string triggerName)
        {
            if (string.IsNullOrEmpty(triggerName)) return;

            var req = new AnimationRequest
            {
                request_id = Guid.NewGuid().ToString(),
                clip_or_procedural_id = triggerName,
                priority = 1
            };
            RequestAnimation(req);
        }

        public void SetLayerWeight(string layerName, float weight)
        {
            if (targetAnimator == null) return;
            int idx = targetAnimator.GetLayerIndex(layerName);
            if (idx >= 0)
            {
                targetAnimator.SetLayerWeight(idx, Mathf.Clamp01(weight));
            }
        }

        public void InterruptCurrent()
        {
            if (_currentActiveRequest != null)
            {
                VivyLogger.Info("AnimationManager", $"Interrupted animation request '{_currentActiveRequest.request_id}'");
                _currentActiveRequest = null;
            }
        }

        private bool HasParameter(string paramName, AnimatorControllerParameterType paramType)
        {
            if (targetAnimator == null || string.IsNullOrEmpty(paramName)) return false;
            foreach (var p in targetAnimator.parameters)
            {
                if (p.name == paramName && p.type == paramType)
                    return true;
            }
            return false;
        }
    }
}
