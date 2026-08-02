using System;
using UnityEngine;

namespace Vivy.Contracts
{
    /// <summary>
    /// Standardized PluginMessage Data Contract (v1.0.0).
    /// Used for inter-plugin message passing across Python and Unity.
    /// </summary>
    [Serializable]
    public class PluginMessage
    {
        public string version = "1.0.0";
        public string source_plugin_id = "";
        public string target_module_id = "";
        public string message_type = "";
        public string payload_json = "";
        public int priority = 0;
        public double timestamp = 0;

        public static PluginMessage FromJson(string json)
        {
            if (string.IsNullOrEmpty(json)) return new PluginMessage();
            try { return JsonUtility.FromJson<PluginMessage>(json); }
            catch (Exception ex)
            {
                Debug.LogWarning($"[Contracts] Failed to parse PluginMessage JSON: {ex.Message}");
                return new PluginMessage();
            }
        }

        public string ToJson() => JsonUtility.ToJson(this);
    }
}
