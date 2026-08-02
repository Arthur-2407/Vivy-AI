using System;
using System.Collections.Generic;
using UnityEngine;
using Vivy.Logging;

namespace Vivy.BehaviorTree
{
    /// <summary>
    /// AI Behavior Scheduler (v1.0.0).
    /// Per Phase 8 of the Master Hyperprompt.
    /// Manages behavior timing, delayed actions, and resource allocation.
    /// </summary>
    public class BehaviorScheduler : MonoBehaviour
    {
        public static BehaviorScheduler Instance { get; private set; }

        private class ScheduledBehavior
        {
            public string id;
            public Action action;
            public float triggerTime;
            public int priority;
        }

        private List<ScheduledBehavior> _scheduled = new List<ScheduledBehavior>();

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
        }

        void Update()
        {
            float now = Time.time;
            for (int i = _scheduled.Count - 1; i >= 0; i--)
            {
                var sb = _scheduled[i];
                if (now >= sb.triggerTime)
                {
                    _scheduled.RemoveAt(i);
                    try
                    {
                        VivyLogger.Info("BehaviorScheduler", $"Executing scheduled behavior '{sb.id}'");
                        sb.action?.Invoke();
                    }
                    catch (Exception ex)
                    {
                        VivyLogger.Error("BehaviorScheduler", $"Scheduled behavior '{sb.id}' failed: {ex.Message}");
                    }
                }
            }
        }

        public string ScheduleBehavior(Action action, float delaySeconds, int priority = 0)
        {
            string id = Guid.NewGuid().ToString();
            _scheduled.Add(new ScheduledBehavior
            {
                id = id,
                action = action,
                triggerTime = Time.time + delaySeconds,
                priority = priority
            });
            return id;
        }
    }
}
