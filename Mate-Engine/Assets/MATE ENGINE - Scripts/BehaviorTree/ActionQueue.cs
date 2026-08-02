using System;
using System.Collections.Generic;
using UnityEngine;
using Vivy.Logging;

namespace Vivy.BehaviorTree
{
    /// <summary>
    /// Action Queue (v1.0.0).
    /// Per Phase 8 of the Master Hyperprompt.
    /// Priority queue for pending actions with timeout handling and cancellation.
    /// </summary>
    public class ActionQueue : MonoBehaviour
    {
        public static ActionQueue Instance { get; private set; }

        public class ActionItem
        {
            public string id;
            public Action action;
            public int priority;
            public float timeoutSeconds;
            public float enqueuedTime;
        }

        private List<ActionItem> _queue = new List<ActionItem>();

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

            // Remove expired actions
            for (int i = _queue.Count - 1; i >= 0; i--)
            {
                var item = _queue[i];
                if (item.timeoutSeconds > 0 && (now - item.enqueuedTime) > item.timeoutSeconds)
                {
                    VivyLogger.Warn("ActionQueue", $"Action '{item.id}' expired after {item.timeoutSeconds}s in queue");
                    _queue.RemoveAt(i);
                }
            }

            // Execute top action if available
            if (_queue.Count > 0)
            {
                var top = _queue[0];
                _queue.RemoveAt(0);
                try
                {
                    VivyLogger.Info("ActionQueue", $"Dequeued and executing action '{top.id}' (Priority: {top.priority})");
                    top.action?.Invoke();
                }
                catch (Exception ex)
                {
                    VivyLogger.Error("ActionQueue", $"Action '{top.id}' execution failed: {ex.Message}");
                }
            }
        }

        public string Enqueue(Action action, int priority = 0, float timeoutSeconds = 10.0f)
        {
            string id = Guid.NewGuid().ToString();
            var item = new ActionItem
            {
                id = id,
                action = action,
                priority = priority,
                timeoutSeconds = timeoutSeconds,
                enqueuedTime = Time.time
            };

            _queue.Add(item);
            _queue.Sort((a, b) => b.priority.CompareTo(a.priority));
            return id;
        }

        public bool Cancel(string actionId)
        {
            int idx = _queue.FindIndex(a => a.id == actionId);
            if (idx >= 0)
            {
                _queue.RemoveAt(idx);
                VivyLogger.Info("ActionQueue", $"Cancelled action '{actionId}'");
                return true;
            }
            return false;
        }

        public void Clear()
        {
            _queue.Clear();
        }
    }
}
