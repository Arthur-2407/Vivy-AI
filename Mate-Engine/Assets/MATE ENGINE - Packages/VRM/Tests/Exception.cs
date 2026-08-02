using System;

namespace VRM.Tests
{
    public class VRMTestException : Exception
    {
        public VRMTestException() : base() { }
        public VRMTestException(string message) : base(message) { }
        public VRMTestException(string message, Exception innerException) : base(message, innerException) { }
    }
}
