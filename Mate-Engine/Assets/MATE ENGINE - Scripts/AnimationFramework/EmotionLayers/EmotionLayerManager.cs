using System.Collections.Generic;
using UnityEngine;
using Vivy.Contracts;
using Vivy.Logging;
using Vivy.AnimationFramework.Procedural;

namespace Vivy.AnimationFramework.EmotionLayers
{
    /// <summary>
    /// Additive Emotion Layer Manager (v1.0.0).
    /// Per Phase 5 of the Master Hyperprompt.
    /// Modulates facial expression, posture, procedural breathing, blink rate,
    /// and gesture intensity continuously based on incoming EmotionState contracts.
    /// </summary>
    public class EmotionLayerManager : MonoBehaviour, IEmotionModifier
    {
        public static EmotionLayerManager Instance { get; private set; }

        public VivyEmotionMapper emotionMapper;
        public ProceduralBreathing proceduralBreathing;
        public ProceduralBlink proceduralBlink;
        public ProceduralSaccade proceduralSaccade;
        public ProceduralWeightShift proceduralWeightShift;

        public EmotionState CurrentState { get; private set; } = new EmotionState();

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;

            if (emotionMapper == null) emotionMapper = GetComponent<VivyEmotionMapper>() ?? GetComponentInParent<VivyEmotionMapper>();
            if (proceduralBreathing == null) proceduralBreathing = GetComponent<ProceduralBreathing>();
            if (proceduralBlink == null) proceduralBlink = GetComponent<ProceduralBlink>();
            if (proceduralSaccade == null) proceduralSaccade = GetComponent<ProceduralSaccade>();
            if (proceduralWeightShift == null) proceduralWeightShift = GetComponent<ProceduralWeightShift>();
        }

        public void ApplyEmotionState(EmotionState state)
        {
            if (state == null) return;
            CurrentState = state;

            VivyLogger.Info("EmotionLayerManager", $"Applying EmotionState: Primary='{state.primary_emotion}', Valence={state.valence:F2}, Arousal={state.arousal:F2}");

            // 1. Forward primary emotion to facial blendshape mapper
            if (emotionMapper != null)
            {
                emotionMapper.SetEmotion(state.primary_emotion);
            }

            // 2. Modulate procedural breathing rate & depth by arousal
            if (proceduralBreathing != null)
            {
                proceduralBreathing.ModulateByEnergy(state.arousal);
            }

            // 3. Modulate blink rate by valence & arousal
            if (proceduralBlink != null)
            {
                // High arousal = faster blinking
                float rateFactor = Mathf.Lerp(1.0f, 0.5f, state.arousal);
                proceduralBlink.minBlinkInterval = 2.0f * rateFactor;
                proceduralBlink.maxBlinkInterval = 5.0f * rateFactor;
            }

            // 4. Modulate weight shift intensity by momentum
            if (proceduralWeightShift != null)
            {
                proceduralWeightShift.weight = Mathf.Clamp01(state.emotional_momentum);
            }
        }
    }
}
