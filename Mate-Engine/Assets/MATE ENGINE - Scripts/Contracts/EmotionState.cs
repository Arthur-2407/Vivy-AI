using System;
using System.Collections.Generic;
using UnityEngine;

namespace Vivy.Contracts
{
    /// <summary>
    /// Standardized EmotionState Data Contract (v1.0.0).
    /// Mirror of Python EmotionState dataclass.
    /// </summary>
    [Serializable]
    public class EmotionState
    {
        public string version = "1.0.0";
        public double timestamp = 0;
        public string primary_emotion = "neutral";
        public SerializableDictionary<string, float> secondary_emotions = new SerializableDictionary<string, float>();
        public SerializableDictionary<string, float> intensity_values = new SerializableDictionary<string, float>();
        public float valence = 0.0f;
        public float arousal = 0.5f;
        public float dominance = 0.5f;
        public string mood_baseline = "calmness";
        public float emotional_momentum = 1.0f;
        public float decay_rate = 7200.0f;

        public static EmotionState FromJson(string json)
        {
            if (string.IsNullOrEmpty(json)) return new EmotionState();
            try
            {
                return JsonUtility.FromJson<EmotionState>(json);
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[Contracts] Failed to parse EmotionState JSON: {ex.Message}");
                return new EmotionState();
            }
        }

        public string ToJson()
        {
            return JsonUtility.ToJson(this);
        }
    }

    [Serializable]
    public class SerializableDictionary<TKey, TValue> : ISerializationCallbackReceiver
    {
        [SerializeField] private List<TKey> keys = new List<TKey>();
        [SerializeField] private List<TValue> values = new List<TValue>();

        private Dictionary<TKey, TValue> dictionary = new Dictionary<TKey, TValue>();

        public Dictionary<TKey, TValue> Dict => dictionary;

        public void OnBeforeSerialize()
        {
            keys.Clear();
            values.Clear();
            foreach (var pair in dictionary)
            {
                keys.Add(pair.Key);
                values.Add(pair.Value);
            }
        }

        public void OnAfterDeserialize()
        {
            dictionary.Clear();
            for (int i = 0; i < Math.Min(keys.Count, values.Count); i++)
            {
                dictionary[keys[i]] = values[i];
            }
        }
    }
}
