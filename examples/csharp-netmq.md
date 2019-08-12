## Connect to ZeroMQ PUB socket using C# and NetMQ

The following example demonstrates how to consume the ZeroMQ PUB socket from C# using the NetMQ library.

````csharp
using (var socket = new SubscriberSocket())
{
    socket.Connect("tcp://localhost:5634");
    socket.SubscribeToAnyTopic();
    
    while (true)
    { 
        using (var stream = new MemoryStream())
        {
            for (; ; )
            {
                var data = socket.ReceiveFrameBytes(out bool more);
                stream.Write(data, 0, data.Length);
                if (more == false)
                {
                    break;
                }
            }
    
            stream.Flush();
            byte[] messageData = stream.ToArray();
            EventMessage message = messageData.Unpack(); // deserialize message-packed object
            if (message != null)
            {

            }
        }
    }
}
````