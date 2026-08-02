using System;
using System.Collections.Generic;
using UnityEngine;

namespace Vivy.Contracts
{
    /// <summary>
    /// Standardized AnimationResponse Data Contract (v1.0.0).
    /// Mirror of Python AnimationResponse dataclass.
    /// </summary>
    [Serializable]
    public class AnimationResponse
    {
        public string version = "1.0.0";
        public string request_id = "";
        public double timestamp = 0;
        public string status = "queued";
        public List<string> resolved_clips = new List<string>();
        public float estimated_duration = 0.0f;
        public string error_message = "";

        public static AnimationResponse FromJson(string json)
        {
            if (string.IsNullOrEmpty(json)) return new AnimationResponse();
            try { return JsonUtility.FromJson<AnimationResponse>(json); }
            catch (Exception ex)
            {
                Debug.LogWarning($"[Contracts] Failed to parse AnimationResponse JSON: {ex.Message}");
                return new AnimationResponse();
            }
        }

        public string ToJson() => JsonUtility.ToJson(this);
    }
}
