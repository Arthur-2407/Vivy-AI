using Vivy.Contracts;

namespace Vivy.AnimationFramework.EmotionLayers
{
    public interface IEmotionModifier
    {
        void ApplyEmotionState(EmotionState state);
        EmotionState CurrentState { get; }
    }
}
