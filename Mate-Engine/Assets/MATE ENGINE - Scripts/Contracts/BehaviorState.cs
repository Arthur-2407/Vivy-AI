using System;
using System.Collections.Generic;
using UnityEngine;

namespace Vivy.Contracts
{
    /// <summary>
    /// Standardized BehaviorState Data Contract (v1.0.0).
    /// Mirror of Python BehaviorState dataclass.
    /// </summary>
    [Serializable]
    public class BehaviorState
    {
        public string version = "1.0.0";
        public double timestamp = 0;
        public string current_mode = "idle";
        public List<string> active_stack = new List<string> { "idle" };
        public string interruption_policy = "interrupt_if_higher";

        public static BehaviorState FromJson(string json)
        {
            if (string.IsNullOrEmpty(json)) return new BehaviorState();
            try { return JsonUtility.FromJson<BehaviorState>(json); }
            catch (Exception ex)
            {
                Debug.LogWarning($"[Contracts] Failed to parse BehaviorState JSON: {ex.Message}");
                return new BehaviorState();
            }
        }

        public string ToJson() => JsonUtility.ToJson(this);
    }
}
