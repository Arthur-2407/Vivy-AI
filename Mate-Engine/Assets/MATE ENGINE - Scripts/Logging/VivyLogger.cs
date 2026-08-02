using System;
using System.Collections.Generic;
using UnityEngine;
using Vivy.Contracts;

namespace Vivy.Logging
{
    public enum LogSeverity
    {
        Trace = 0,
        Debug = 1,
        Info = 2,
        Warn = 3,
        Error = 4,
        Fatal = 5
    }

    /// <summary>
    /// Structured Logging System for Unity side (v1.0.0).
    /// Per Rule 11 of the Master Hyperprompt.
    /// Categorized logging with DiagnosticEvent support.
    /// </summary>
    public static class VivyLogger
    {
        public static LogSeverity MinimumSeverity = LogSeverity.Info;
        private static readonly Dictionary<string, float> _metrics = new Dictionary<string, float>();

        public static DiagnosticEvent Log(string moduleName, string message, LogSeverity severity = LogSeverity.Info, string eventType = "general")
        {
            var diagEvent = new DiagnosticEvent
            {
                timestamp = DateTime.UtcNow.Subtract(new DateTime(1970, 1, 1)).TotalSeconds,
                module_id = moduleName,
                event_type = eventType,
                severity = severity.ToString().ToUpper(),
                message = message,
                stack_context = Environment.StackTrace
            };

            if (severity >= MinimumSeverity)
            {
                string formatted = $"[VivyLog] [{diagEvent.severity}] [{moduleName}] {message}";
                switch (severity)
                {
                    case LogSeverity.Trace:
                    case LogSeverity.Debug:
                    case LogSeverity.Info:
                        Debug.Log(formatted);
                        break;
                    case LogSeverity.Warn:
                        Debug.LogWarning(formatted);
                        break;
                    case LogSeverity.Error:
                    case LogSeverity.Fatal:
                        Debug.LogError(formatted);
                        break;
                }
            }

            return diagEvent;
        }

        public static void Info(string module, string msg)  => Log(module, msg, LogSeverity.Info);
        public static void DebugLog(string module, string msg) => Log(module, msg, LogSeverity.Debug);
        public static void Warn(string module, string msg)  => Log(module, msg, LogSeverity.Warn);
        public static void Error(string module, string msg) => Log(module, msg, LogSeverity.Error);

        public static void RecordMetric(string metricName, float value)
        {
            _metrics[metricName] = value;
            Log("Performance", $"Metric {metricName} = {value}", LogSeverity.Debug, "metric");
        }
    }
}
