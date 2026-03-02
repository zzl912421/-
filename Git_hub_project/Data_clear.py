#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动化测试数据管理通用模板
核心功能：解决测试数据硬编码、数据污染、环境残留问题
适用场景：接口测试/UI测试/电商测试等需要动态数据的场景
支持存储：MySQL/Redis（可扩展至MongoDB等）
作者：测试开发工程师
版本：v1.0
"""

import random
import string
import time
import pymysql
import redis
from contextlib import contextmanager

# ======================== 配置项（使用前必须修改）========================
# 1. MySQL数据库配置（根据实际测试环境调整）
MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "test_user",
    "password": "test_pass",
    "db": "test_db",
    "charset": "utf8mb4"
}

# 2. Redis配置（若不用Redis可注释）
REDIS_CONFIG = {
    "host": "127.0.0.1",
    "port": 6379,
    "password": "",
    "db": 0
}

# 3. 数据生成规则（可根据业务自定义）
# 随机字符串长度
RAND_STR_LENGTH = 8
# 手机号前缀（适配国内手机号规则）
PHONE_PREFIX = "138"


# ======================== 工具类：数据库连接管理 =========================
@contextmanager
def mysql_connect():
    """
    MySQL上下文管理器：自动创建/关闭连接，避免连接泄露
    使用方式：with mysql_connect() as conn: 操作数据库
    """
    conn = None
    cursor = None
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor(pymysql.cursors.DictCursor)  # 返回字典格式结果
        yield cursor, conn
    except pymysql.MySQLError as e:
        print(f"MySQL连接/执行失败：{e}")
        raise  # 抛出异常，让测试用例感知失败
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@contextmanager
def redis_connect():
    """Redis上下文管理器：自动创建/关闭连接"""
    r = None
    try:
        r = redis.Redis(**REDIS_CONFIG)
        yield r
    except redis.RedisError as e:
        print(f"Redis连接/执行失败：{e}")
        raise
    finally:
        if r:
            r.close()


# ======================== 核心功能：动态生成测试数据 =========================
class TestDataGenerator:
    """测试数据生成器：支持生成常用测试数据类型，可扩展"""

    @staticmethod
    def generate_random_str(length=RAND_STR_LENGTH, include_digits=True):
        """
        生成随机字符串（用于用户名/订单号等）
        :param length: 字符串长度
        :param include_digits: 是否包含数字
        :return: 随机字符串
        """
        if include_digits:
            chars = string.ascii_letters + string.digits
        else:
            chars = string.ascii_letters
        return ''.join(random.choice(chars) for _ in range(length))

    @staticmethod
    def generate_phone():
        """生成随机手机号（符合国内格式）"""
        suffix = ''.join(random.choice(string.digits) for _ in range(8))
        return PHONE_PREFIX + suffix

    @staticmethod
    def generate_order_id():
        """生成唯一订单号（时间戳+随机数，避免重复）"""
        timestamp = str(int(time.time() * 1000))  # 毫秒级时间戳
        random_num = ''.join(random.choice(string.digits) for _ in range(4))
        return f"ORD{timestamp}{random_num}"


# ======================== 核心功能：测试数据管理（生成+清理）========================
class TestDataManager:
    """测试数据管理器：统一管理数据的创建与清理"""

    def __init__(self):
        self.generator = TestDataGenerator()
        # 存储需要清理的数据ID（如用户ID/订单ID），用例结束后批量清理
        self.need_clean_data = {
            "mysql_user_ids": [],
            "mysql_order_ids": [],
            "redis_keys": []
        }

    def create_test_user(self):
        """
        示例：创建测试用户（电商场景）
        :return: 生成的用户信息（dict）
        """
        # 1. 生成动态数据
        username = f"test_{self.generator.generate_random_str()}"
        phone = self.generator.generate_phone()
        password = "Test@123456"  # 固定密码（也可动态生成）

        # 2. 插入数据库
        with mysql_connect() as (cursor, conn):
            sql = """
            INSERT INTO users (username, phone, password, create_time)
            VALUES (%s, %s, %s, NOW())
            """
            cursor.execute(sql, (username, phone, password))
            conn.commit()
            user_id = cursor.lastrowid  # 获取自增ID

        # 3. 记录需要清理的用户ID
        self.need_clean_data["mysql_user_ids"].append(user_id)
        print(f"创建测试用户成功：ID={user_id}, 手机号={phone}")
        return {"user_id": user_id, "username": username, "phone": phone, "password": password}

    def create_test_order(self, user_id):
        """
        示例：创建测试订单（依赖用户ID）
        :param user_id: 关联的用户ID
        :return: 订单信息（dict）
        """
        order_id = self.generator.generate_order_id()
        amount = round(random.uniform(10.0, 1000.0), 2)  # 随机订单金额（10-1000元）

        # 1. 插入订单表
        with mysql_connect() as (cursor, conn):
            sql = """
            INSERT INTO orders (order_id, user_id, amount, status, create_time)
            VALUES (%s, %s, %s, 'pending', NOW())
            """
            cursor.execute(sql, (order_id, user_id, amount))
            conn.commit()

        # 2. 存入Redis（模拟订单缓存）
        with redis_connect() as r:
            redis_key = f"order:{order_id}"
            r.set(redis_key, f"user_{user_id}_amount_{amount}")
            r.expire(redis_key, 3600)  # 设置1小时过期（可选）

        # 3. 记录需要清理的订单ID和RedisKey
        self.need_clean_data["mysql_order_ids"].append(order_id)
        self.need_clean_data["redis_keys"].append(redis_key)
        print(f"创建测试订单成功：订单ID={order_id}, 金额={amount}")
        return {"order_id": order_id, "user_id": user_id, "amount": amount}

    def clean_all_data(self):
        """
        清理所有生成的测试数据（用例执行完必须调用）
        原则：先清理关联数据（订单），再清理主数据（用户）
        """
        print("开始清理测试数据...")

        # 1. 清理MySQL订单数据
        if self.need_clean_data["mysql_order_ids"]:
            with mysql_connect() as (cursor, conn):
                placeholders = ','.join(['%s'] * len(self.need_clean_data["mysql_order_ids"]))
                sql = f"DELETE FROM orders WHERE order_id IN ({placeholders})"
                cursor.execute(sql, tuple(self.need_clean_data["mysql_order_ids"]))
                conn.commit()
                print(f"清理订单数据：共{cursor.rowcount}条")

        # 2. 清理MySQL用户数据
        if self.need_clean_data["mysql_user_ids"]:
            with mysql_connect() as (cursor, conn):
                placeholders = ','.join(['%s'] * len(self.need_clean_data["mysql_user_ids"]))
                sql = f"DELETE FROM users WHERE id IN ({placeholders})"
                cursor.execute(sql, tuple(self.need_clean_data["mysql_user_ids"]))
                conn.commit()
                print(f"清理用户数据：共{cursor.rowcount}条")

        # 3. 清理Redis数据
        if self.need_clean_data["redis_keys"]:
            with redis_connect() as r:
                deleted_count = r.delete(*self.need_clean_data["redis_keys"])
                print(f"清理Redis数据：共{deleted_count}个Key")

        # 4. 清空待清理列表（避免重复清理）
        self.need_clean_data = {
            "mysql_user_ids": [],
            "mysql_order_ids": [],
            "redis_keys": []
        }
        print("测试数据清理完成！")


# ======================== 用法示例（测试用例中调用）========================
def test_demo():
    """
    示例：测试用例中使用数据管理模板
    流程：创建数据→执行测试操作→清理数据
    """
    # 1. 初始化数据管理器
    data_manager = TestDataManager()

    try:
        # 2. 生成测试数据
        user_info = data_manager.create_test_user()
        order_info = data_manager.create_test_order(user_info["user_id"])

        # 3. 执行测试操作（此处替换为实际测试逻辑，如接口调用/UI操作）
        print(f"执行测试：用户{user_info['user_id']}下单{order_info['order_id']}")
        # 模拟测试操作...

    finally:
        # 4. 无论测试成功/失败，都清理数据（关键！）
        data_manager.clean_all_data()


# ======================== 注意事项（必看）========================
"""
1. 环境依赖安装：
   pip install pymysql redis

2. 配置项修改：
   - 必须修改MYSQL_CONFIG/REDIS_CONFIG为实际测试环境信息；
   - 根据业务调整数据生成规则（如手机号前缀、订单号格式）；
   - 扩展存储类型（如MongoDB）：新增对应的连接管理器和数据操作方法。

3. 扩展自定义数据：
   - 新增create_test_xxx方法（如create_test_product创建商品）；
   - 在need_clean_data中添加对应清理字段，并重写clean_all_data。

4. 异常处理：
   - 数据库操作异常会主动抛出，确保测试用例能感知失败；
   - 上下文管理器自动关闭连接，避免连接泄露。

5. 复用建议：
   - 将此模板放入测试项目的common/utils目录；
   - 测试用例中导入TestDataManager类直接使用。
"""

if __name__ == "__main__":
    # 运行示例
    test_demo()