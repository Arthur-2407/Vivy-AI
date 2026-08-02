namespace Vivy.AnimationFramework
{
    public interface ITransitionManager
    {
        void TransitionToState(string stateName, float crossfadeDuration = 0.25f, int layerIndex = 0);
        bool IsTransitioning(int layerIndex = 0);
    }
}
