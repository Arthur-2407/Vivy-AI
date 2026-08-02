using System.Collections;
using UnityEngine;

namespace Vivy.AnimationFramework.Procedural
{
    /// <summary>
    /// Procedural Eye Saccades Layer (v1.0.0).
    /// Per Phase 4 of the Master Hyperprompt.
    /// Simulates micro eye movements between fixation points.
    /// </summary>
    public class ProceduralSaccade : MonoBehaviour, IProceduralMotion
    {
        public bool isEnabled = true;
        [Range(0f, 1f)] public float weight = 1.0f;
        public float saccadeIntervalMin = 0.8f;
        public float saccadeIntervalMax = 3.0f;
        public float microShiftMaxDegrees = 2.0f;

        public bool IsEnabled { get => isEnabled; set => isEnabled = value; }
        public float Weight { get => weight; set => weight = value; }

        public Vector2 CurrentSaccadeOffset { get; private set; }

        private float _nextSaccadeTime;

        void Start()
        {
            ScheduleNextSaccade();
        }

        void Update()
        {
            if (!isEnabled || weight <= 0.001f) return;
            UpdateMotion(Time.deltaTime);
        }

        public void UpdateMotion(float deltaTime)
        {
            if (Time.time >= _nextSaccadeTime)
            {
                float offsetX = Random.Range(-microShiftMaxDegrees, microShiftMaxDegrees) * weight;
                float offsetY = Random.Range(-microShiftMaxDegrees, microShiftMaxDegrees) * weight;
                CurrentSaccadeOffset = new Vector2(offsetX, offsetY);
                ScheduleNextSaccade();
            }
        }

        private void ScheduleNextSaccade()
        {
            _nextSaccadeTime = Time.time + Random.Range(saccadeIntervalMin, saccadeIntervalMax);
        }
    }
}
