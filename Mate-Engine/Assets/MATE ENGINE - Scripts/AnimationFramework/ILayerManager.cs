namespace Vivy.AnimationFramework
{
    public interface ILayerManager
    {
        void SetLayerWeight(int layerIndex, float weight, float duration = 0f);
        void SetLayerWeight(string layerName, float weight, float duration = 0f);
        float GetLayerWeight(string layerName);
        int GetLayerIndex(string layerName);
    }
}
