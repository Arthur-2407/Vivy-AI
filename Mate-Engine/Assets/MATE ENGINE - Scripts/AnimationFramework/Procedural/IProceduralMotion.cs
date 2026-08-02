namespace Vivy.AnimationFramework.Procedural
{
    public interface IProceduralMotion
    {
        bool IsEnabled { get; set; }
        float Weight { get; set; }
        void UpdateMotion(float deltaTime);
    }
}
