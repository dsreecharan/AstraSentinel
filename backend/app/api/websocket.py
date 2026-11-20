from anyio import create_task_group
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.events import event_message

router = APIRouter()


@router.websocket("/ws/events")
async def events(socket: WebSocket) -> None:
    if socket.headers.getlist("origin") != [socket.app.state.frontend_origin]:
        await socket.close(code=1008)
        return

    with socket.app.state.broker.subscribe() as subscription:
        try:
            await socket.accept()
            await socket.send_json(event_message("ready").model_dump(mode="json"))
            close_code = None
            async with create_task_group() as tasks:
                async def send_events() -> None:
                    try:
                        while True:
                            event = await subscription.events.get()
                            await socket.send_json(event.model_dump(mode="json"))
                    except WebSocketDisconnect:
                        tasks.cancel_scope.cancel()

                async def watch_client() -> None:
                    nonlocal close_code
                    message = await socket.receive()
                    close_code = 1008 if message["type"] == "websocket.receive" else None
                    tasks.cancel_scope.cancel()

                async def watch_overflow() -> None:
                    nonlocal close_code
                    await subscription.overflow.wait()
                    close_code = 1013
                    tasks.cancel_scope.cancel()

                tasks.start_soon(send_events)
                tasks.start_soon(watch_client)
                tasks.start_soon(watch_overflow)
            if close_code is not None:
                await socket.close(code=close_code)
        except WebSocketDisconnect:
            return
