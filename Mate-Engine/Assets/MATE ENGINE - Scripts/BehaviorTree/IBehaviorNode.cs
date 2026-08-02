namespace Vivy.BehaviorTree
{
    public enum NodeStatus
    {
        Ready,
        Running,
        Success,
        Failure
    }

    public interface IBehaviorNode
    {
        string Name { get; }
        int Priority { get; }
        NodeStatus Status { get; }
        NodeStatus Execute(float deltaTime);
        void Reset();
    }
}
