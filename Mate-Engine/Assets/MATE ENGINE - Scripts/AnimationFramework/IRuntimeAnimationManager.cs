using Vivy.Contracts;

namespace Vivy.AnimationFramework
{
    public interface IRuntimeAnimationManager
    {
        AnimationResponse RequestAnimation(AnimationRequest request);
        void PlayTrigger(string triggerName);
        void SetLayerWeight(string layerName, float weight);
        void InterruptCurrent();
    }
}
