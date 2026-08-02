namespace Vivy.AnimationFramework
{
    public interface IBlendManager
    {
        void SetBlendParameter(string paramName, float value, float smoothDuration = 0f);
        float GetBlendParameter(string paramName);
    }
}
