using System;
using System.Collections.Generic;
using UnityEngine;

namespace Vivy.Contracts
{
    /// <summary>
    /// Standardized AnimationRequest Data Contract (v1.0.0).
    /// Mirror of Python AnimationRequest dataclass.
    /// </summary>
    [Serializable]
    public class AnimationRequest
    {
        public string version = "1.0.0";
        public string request_id = "";
        public double timestamp = 0;
        public string category = "idle";
        public string clip_or_procedural_id = "";
        public List<string> target_layers = new List<string> { "Base Layer" };
        public float blend_weight = 1.0f;
        public float transition_duration = 0.3f;
        public int priority = 0;
        public string interruption_policy = "interrupt_if_higher";
        public string source_module = "AnimationPlanner";

        public static AnimationRequest FromJson(string json)
        {
            if (string.IsNullOrEmpty(json)) return new AnimationRequest();
            try { return JsonUtility.FromJson<AnimationRequest>(json); }
            catch (Exception ex)
            {
                Debug.LogWarning($"[Contracts] Failed to parse AnimationRequest JSON: {ex.Message}");
                return new AnimationRequest();
            }
        }

        public string ToJson() => JsonUtility.ToJson(this);
    }
}
