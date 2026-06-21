import os

# ==========================================
# 代理驱逐大军：在引入任何网络库之前，斩断所有可能的代理环境变量
# ==========================================
proxy_keys = ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']
for key in proxy_keys:
    if key in os.environ:
        del os.environ[key]

# 强制设置为空，双重保险
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''

# 在清理完代理之后，再 import akshare
import akshare as ak
import pandas as pd
import time

def test_akshare_connection():
    print("🚀 开始测试 AkShare 连通性 (强制直连模式)...")
    print("目标：获取 '平安银行(000001)' 的 [后复权] 历史行情数据\n")
    
    try:
        start_time = time.time()
        
        # 调用东方财富接口
        df = ak.stock_zh_a_hist(
            symbol="000001", 
            period="daily", 
            start_date="20240101", 
            end_date="20240110", 
            adjust="hfq"
        )
        
        elapsed_time = time.time() - start_time
        
        if df is not None and not df.empty:
            print(f"✅ 测试成功！耗时: {elapsed_time:.2f} 秒")
            print("-" * 40)
            print("成功获取的数据片段 (注意看'收盘'价是否已后复权):")
            print(df[['日期', '开盘', '收盘', '最高', '最低', '成交量', '成交额']].head(3))
            print("-" * 40)
            return True
        else:
            print("❌ 测试失败：接口返回了空数据。")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败：发生了网络连接或解析错误。")
        print(f"错误详情:\n{e}")
        return False

if __name__ == "__main__":
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    
    test_akshare_connection()