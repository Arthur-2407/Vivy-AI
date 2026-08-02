using System;
using UnityEngine;

namespace Vivy.Contracts
{
    /// <summary>
    /// Standardized CognitiveOutput Data Contract (v1.0.0).
    /// Mirror of Python CognitiveOutput dataclass.
    /// </summary>
    [Serializable]
    public class CognitiveOutput
    {
        public string version = "1.0.0";
        public double timestamp = 0;
        public string response_text = "";
        public string emotional_intent = "neutral";
        public string behavioral_intent = "talk";
        public string reasoning_trace = "";
        public float confidence_score = 1.0f;

        public static CognitiveOutput FromJson(string json)
        {
            if (string.IsNullOrEmpty(json)) return new CognitiveOutput();
            try { return JsonUtility.FromJson<CognitiveOutput>(json); }
            catch (Exception ex)
            {
                Debug.LogWarning($"[Contracts] Failed to parse CognitiveOutput JSON: {ex.Message}");
                return new CognitiveOutput();
            }
        }

        public string ToJson() => JsonUtility.ToJson(this);
    }
}
