using System;
using UnityEngine;

namespace Vivy.Contracts
{
    /// <summary>
    /// Standardized DiagnosticEvent Data Contract (v1.0.0).
    /// Mirror of Python DiagnosticEvent dataclass.
    /// </summary>
    [Serializable]
    public class DiagnosticEvent
    {
        public string version = "1.0.0";
        public double timestamp = 0;
        public string module_id = "Unknown";
        public string event_type = "general";
        public string severity = "INFO";
        public string message = "";
        public string stack_context = "";

        public static DiagnosticEvent FromJson(string json)
        {
            if (string.IsNullOrEmpty(json)) return new DiagnosticEvent();
            try { return JsonUtility.FromJson<DiagnosticEvent>(json); }
            catch (Exception ex)
            {
                Debug.LogWarning($"[Contracts] Failed to parse DiagnosticEvent JSON: {ex.Message}");
                return new DiagnosticEvent();
            }
        }

        public string ToJson() => JsonUtility.ToJson(this);
    }
}
