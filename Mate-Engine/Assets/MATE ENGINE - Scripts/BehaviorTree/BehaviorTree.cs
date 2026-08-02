using System.Collections.Generic;
using UnityEngine;
using Vivy.Logging;

namespace Vivy.BehaviorTree
{
    /// <summary>
    /// AI Behavior Tree Engine (v1.0.0).
    /// Per Phase 8 of the Master Hyperprompt.
    /// Supports priority arbitration, multitasking, utility scoring, and interrupt handling.
    /// </summary>
    public class BehaviorTree : MonoBehaviour
    {
        public static BehaviorTree Instance { get; private set; }

        private List<IBehaviorNode> _rootNodes = new List<IBehaviorNode>();
        private IBehaviorNode _activeNode;

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
        }

        void Update()
        {
            TickTree(Time.deltaTime);
        }

        public void AddRootNode(IBehaviorNode node)
        {
            if (node != null && !_rootNodes.Contains(node))
            {
                _rootNodes.Add(node);
                // Sort by priority descending
                _rootNodes.Sort((a, b) => b.Priority.CompareTo(a.Priority));
            }
        }

        public void TickTree(float deltaTime)
        {
            if (_rootNodes.Count == 0) return;

            // Evaluate highest priority ready node
            for (int i = 0; i < _rootNodes.Count; i++)
            {
                var node = _rootNodes[i];
                if (_activeNode != null && node.Priority > _activeNode.Priority && _activeNode.Status == NodeStatus.Running)
                {
                    VivyLogger.Info("BehaviorTree", $"Node '{node.Name}' (Priority {node.Priority}) interrupted '{_activeNode.Name}' (Priority {_activeNode.Priority})");
                    _activeNode.Reset();
                    _activeNode = node;
                }

                if (_activeNode == null) _activeNode = node;

                NodeStatus status = _activeNode.Execute(deltaTime);
                if (status != NodeStatus.Running)
                {
                    _activeNode.Reset();
                    _activeNode = null;
                }
                if (status == NodeStatus.Failure) continue;
                break;
            }
        }
    }
}
