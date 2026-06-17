#!/bin/bash
# ============================================================
# 牛津词典 Web 服务 - 启动脚本
# ============================================================
# 用法: ./start.sh [start|stop|restart|status|install|uninstall]
# ============================================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.oxford.dictionary"
PLIST_PATH="$PROJECT_DIR/$PLIST_NAME.plist"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"

case "${1:-start}" in
    start)
        echo "🚀 启动牛津词典服务..."
        python3 "$PROJECT_DIR/server.py"
        ;;
    background)
        echo "🚀 后台启动牛津词典服务..."
        nohup python3 "$PROJECT_DIR/server.py" > "$LOG_DIR/stdout.log" 2> "$LOG_DIR/stderr.log" &
        echo "PID: $!"
        echo "服务已后台启动，访问: http://localhost:18310"
        ;;
    stop)
        echo "🛑 停止牛津词典服务..."
        pkill -f "python3.*server.py" 2>/dev/null || echo "服务未运行"
        ;;
    restart)
        $0 stop
        sleep 1
        $0 background
        ;;
    status)
        PID=$(pgrep -f "python3.*server.py" 2>/dev/null)
        if [ -n "$PID" ]; then
            echo "✅ 服务运行中 (PID: $PID)"
            echo "   访问: http://localhost:18310"
            curl -s -o /dev/null -w "   API状态: %{http_code}\n" 'http://localhost:18310/api/search?q=test'
        else
            echo "❌ 服务未运行"
        fi
        ;;
    install)
        echo "📦 安装开机自启动服务..."
        cp "$PLIST_PATH" ~/Library/LaunchAgents/
        launchctl load ~/Library/LaunchAgents/"$PLIST_NAME.plist"
        echo "✅ 已安装，服务将在开机时自动启动"
        ;;
    uninstall)
        echo "🗑️ 卸载开机自启动服务..."
        launchctl unload ~/Library/LaunchAgents/"$PLIST_NAME.plist" 2>/dev/null
        rm -f ~/Library/LaunchAgents/"$PLIST_NAME.plist"
        echo "✅ 已卸载"
        ;;
    *)
        echo "用法: $0 [start|stop|restart|status|install|uninstall]"
        echo ""
        echo "   start      前台启动服务"
        echo "   background 后台启动服务"
        echo "   stop       停止服务"
        echo "   restart    重启服务"
        echo "   status     查看服务状态"
        echo "   install    安装开机启动（launchd）"
        echo "   uninstall  移除开机启动"
        ;;
esac
