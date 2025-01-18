#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests
import logging
from typing import Dict, List, Optional, Union
from datetime import datetime
import json
import time
import os

logger = logging.getLogger(__name__)

class FeishuAPI:
    """飞书API封装类"""
    
    BASE_URL = "https://open.feishu.cn/open-apis"
    
    def __init__(self, app_id: str, app_secret: str):
        """初始化飞书API客户端
        Args:
            app_id: 应用ID
            app_secret: 应用密钥
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self.BASE_URL = "https://open.feishu.cn/open-apis"
        self.access_token = None
        self.token_expire_time = 0  # token过期时间戳
        
    def _get_tenant_access_token(self) -> Optional[str]:
        """获取tenant_access_token
        Returns:
            str: 成功返回token，失败返回None
        """
        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        headers = {
            "Content-Type": "application/json; charset=utf-8"
        }
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            token_data = response.json()
            
            if token_data.get('code') == 0:
                return token_data.get('tenant_access_token')
            else:
                logger.error(f"Error getting token: {token_data}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get tenant access token: {str(e)}")
            return None
            
    def _ensure_token(self) -> bool:
        """确保有有效的访问令牌
        Returns:
            bool: 成功返回True，失败返回False
        """
        # 如果没有token或token已过期，重新获取
        if not self.access_token or time.time() >= self.token_expire_time:
            logger.info("Token不存在或已过期，重新获取...")
            try:
                url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
                payload = {
                    "app_id": self.app_id,
                    "app_secret": self.app_secret
                }
                response = requests.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                if data.get('code') != 0:
                    logger.error(f"获取token失败: {data}")
                    return False
                    
                self.access_token = data.get('tenant_access_token')
                self.token_expire_time = time.time() + data.get('expire', 7200)
                logger.info(f"成功获取新token: {self.access_token[:10]}...")
                
            except Exception as e:
                logger.error(f"获取token时发生错误: {str(e)}")
                return False
                
        return True
        
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头
        Returns:
            Dict[str, str]: 请求头
        """
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {self.access_token}"
        }
        logger.debug(f"Request headers: {headers}")
        return headers
        
    def get_table_metadata(self, app_token: str) -> Optional[Dict]:
        """获取多维表格元数据
        Args:
            app_token: 多维表格的应用token
        Returns:
            Dict: 成功返回元数据，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}"
        
        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get table metadata: {str(e)}")
            return None
            
    def create_table(self, app_token: str, table: Dict) -> Optional[Dict]:
        """创建数据表
        Args:
            app_token: 多维表格的应用token
            table: 表格定义，包含name和fields
        Returns:
            Dict: 成功返回创建的表格信息，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables"
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=table)
            response.raise_for_status()
            result = response.json()
            if result.get('code') != 0:
                logger.error(f"Failed to create table: {json.dumps(result, ensure_ascii=False)}")
            return result
        except Exception as e:
            logger.error(f"Failed to create table: {str(e)}")
            return None
            
    def list_records(self, app_token: str, table_id: str, page_size: int = 20) -> Optional[Dict]:
        """获取表格中的记录
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            page_size: 每页记录数
        Returns:
            Dict: 成功返回记录列表，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        params = {"page_size": page_size}
        
        try:
            response = requests.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to list records: {str(e)}")
            return None
            
    def create_record(self, app_token: str, table_id: str, fields: Dict) -> Optional[Dict]:
        """创建单条记录
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            fields: 记录字段
        Returns:
            Dict: 成功返回创建的记录，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=fields)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to create record: {str(e)}")
            return None
            
    def batch_create_records(self, app_token: str, table_id: str, records: List[Dict]) -> Optional[Dict]:
        """批量创建记录
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            records: 记录列表
        Returns:
            Dict: 成功返回创建的记录列表，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
        payload = {"records": records}
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to batch create records: {str(e)}")
            return None
            
    def search_records(self, 
                      app_token: str, 
                      table_id: str, 
                      field_names: List[str],
                      filter_conditions: Optional[Dict] = None) -> Optional[List[Dict]]:
        """搜索记录
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            field_names: 要返回的字段名列表
            filter_conditions: 过滤条件,格式为:
                {
                    "conjunction": "and",
                    "conditions": [
                        {
                            "field_name": "字段名",
                            "operator": "contains",
                            "value": ["值"]
                        }
                    ]
                }
        Returns:
            List[Dict]: 成功返回搜索结果，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/search"
        
        # 构建请求体
        payload = {
            "page_size": 100,  # 每页记录数
            "field_names": field_names,
            "automatic_fields": False  # 不返回自动计算的字段
        }
        
        if filter_conditions:
            payload["filter"] = filter_conditions
            
        results = []
        page_token = None
        
        while True:
            try:
                if page_token:
                    payload["page_token"] = page_token
                    
                logger.info(f"Search request payload: {payload}")  # 添加日志
                response = requests.post(url, headers=self._get_headers(), json=payload)
                response.raise_for_status()
                data = response.json()
                
                if data.get('code') != 0:
                    logger.error(f"Search failed: {data}")
                    return None
                    
                items = data.get('data', {}).get('items', [])
                results.extend(items)
                
                if not data.get('data', {}).get('has_more', False):
                    break
                    
                page_token = data.get('data', {}).get('page_token')
                
            except Exception as e:
                logger.error(f"Failed to search records: {str(e)}")
                if hasattr(e, 'response'):
                    logger.error(f"Response content: {e.response.content}")
                return None
                
        return results

    def update_record(self, app_token: str, table_id: str, record_id: str, fields: Dict) -> Optional[Dict]:
        """更新单条记录
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            record_id: 记录ID
            fields: 要更新的字段
        Returns:
            Dict: 成功返回更新后的记录，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        
        try:
            response = requests.put(url, headers=self._get_headers(), json=fields)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to update record: {str(e)}")
            return None

    def batch_update_records(self, app_token: str, table_id: str, records: List[Dict]) -> Optional[Dict]:
        """批量更新记录
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            records: 记录列表，每条记录必须包含record_id和fields字段
        Returns:
            Dict: 成功返回更新的记录列表，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update"
        payload = {"records": records}
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to batch update records: {str(e)}")
            return None

    def delete_record(self, app_token: str, table_id: str, record_id: str) -> Optional[Dict]:
        """删除单条记录
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            record_id: 记录ID
        Returns:
            Dict: 成功返回删除结果，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        
        try:
            response = requests.delete(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to delete record: {str(e)}")
            return None

    def batch_delete_records(self, app_token: str, table_id: str, record_ids: List[str]) -> Optional[Dict]:
        """批量删除记录
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            record_ids: 记录ID列表
        Returns:
            Dict: 成功返回删除结果，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete"
        
        # 按照API文档格式构建请求体
        payload = {
            "records": record_ids
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to batch delete records: {str(e)}")
            return None

    def list_fields(self, app_token: str, table_id: str, page_size: int = 20, 
                   view_id: Optional[str] = None, text_field_as_array: bool = False) -> Optional[Dict]:
        """获取数据表中的所有字段
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            page_size: 每页记录数
            view_id: 视图ID（可选）
            text_field_as_array: 是否将字段描述以数组形式返回
        Returns:
            Dict: 成功返回字段列表，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
        params = {
            "page_size": page_size,
            "text_field_as_array": text_field_as_array
        }
        if view_id:
            params["view_id"] = view_id
            
        try:
            response = requests.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to list fields: {str(e)}")
            return None

    def create_field(self, 
                    app_token: str, 
                    table_id: str, 
                    field_name: str,
                    field_type: int,
                    property: Optional[Dict] = None) -> Optional[Dict]:
        """创建字段
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            field_name: 字段名称
            field_type: 字段类型，参考飞书API文档
            property: 字段属性（可选）
            
        Returns:
            Dict: 成功返回字段信息，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
        
        payload = {
            "field_name": field_name,
            "type": field_type
        }
        if property is not None:
            payload["property"] = property
            
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to create field: {str(e)}")
            return None

    def update_field(self,
                    app_token: str,
                    table_id: str,
                    field_id: str,
                    field_name: Optional[str] = None,
                    property: Optional[Dict] = None) -> Optional[Dict]:
        """更新字段
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            field_id: 字段ID
            field_name: 新的字段名称（可选）
            property: 新的字段属性（可选）
            
        Returns:
            Dict: 成功返回更新后的字段信息，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{field_id}"
        
        payload = {}
        if field_name is not None:
            payload["field_name"] = field_name
        if property is not None:
            payload["property"] = property
            
        try:
            response = requests.put(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to update field: {str(e)}")
            return None

    def delete_field(self, app_token: str, table_id: str, field_id: str) -> Optional[Dict]:
        """删除字段
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            field_id: 字段ID
            
        Returns:
            Dict: 成功返回删除结果，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{field_id}"
        
        try:
            response = requests.delete(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to delete field: {str(e)}")
            return None

    def upload_file(self, file_obj, file_name: str, parent_type: str = "bitable_file", parent_node: Optional[str] = None) -> Optional[Dict]:
        """上传文件
        Args:
            file_obj: 文件对象（已打开的文件）
            file_name: 文件名
            parent_type: 上传位置类型，默认为 bitable_file（上传到多维表格）
            parent_node: 上传位置的节点ID（对于多维表格，是 app_token）
        Returns:
            Dict: 成功返回包含file_token的响应，失败返回None
        """
        if not self._ensure_token():
            return None
        
        url = f"{self.BASE_URL}/drive/v1/files/upload_all"
        
        # 获取文件大小
        file_obj.seek(0, 2)
        file_size = file_obj.tell()
        file_obj.seek(0)
        
        from requests_toolbelt import MultipartEncoder
        
        form = {
            'file_name': file_name,
            'parent_type': parent_type,
            'size': str(file_size),
            'file': (file_name, file_obj, 'application/octet-stream')
        }
        
        if parent_node:
            form['parent_node'] = parent_node
        
        multi_form = MultipartEncoder(form)
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': multi_form.content_type
        }
        
        try:
            response = requests.post(url, headers=headers, data=multi_form)
            response.raise_for_status()
            result = response.json()
            logger.debug(f"Upload response: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to upload file: {str(e)}")
            if hasattr(e, 'response'):
                logger.error(f"Response content: {e.response.content}")
            return None

    def list_tables(self, app_token: str, page_size: int = 20, page_token: Optional[str] = None) -> Optional[Dict]:
        """列出多维表格中的所有数据表
        
        Args:
            app_token: 多维表格的应用token
            page_size: 分页大小，默认20，最大100
            page_token: 分页标记，第一次请求不填
            
        Returns:
            Dict: 成功返回表格列表，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables"
        params = {
            "page_size": min(page_size, 100)  # 确保不超过最大限制
        }
        if page_token:
            params["page_token"] = page_token
            
        try:
            response = requests.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to list tables: {str(e)}")
            return None

    def copy_table(self, app_token: str, table_id: str, dest_app_token: Optional[str] = None) -> Optional[Dict]:
        """复制数据表
        
        Args:
            app_token: 源多维表格的应用token
            table_id: 要复制的表格ID
            dest_app_token: 目标多维表格的应用token，不填则复制到同一个多维表格
            
        Returns:
            Dict: 成功返回新表格信息，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/copy"
        payload = {}
        if dest_app_token:
            payload["dst_app_token"] = dest_app_token
            
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to copy table: {str(e)}")
            return None

    def update_table(self, app_token: str, table_id: str, name: str) -> Optional[Dict]:
        """更新数据表名称
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            name: 新的数据表名称
            
        Returns:
            Dict: 成功返回更新结果，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}"
        
        payload = {
            "name": name
        }
        
        try:
            response = requests.patch(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to update table: {str(e)}")
            return None

    def delete_table(self, app_token: str, table_id: str) -> Optional[Dict]:
        """删除数据表
        
        Args:
            app_token: 多维表格的应用token
            table_id: 要删除的表格ID
            
        Returns:
            Dict: 成功返回删除结果，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}"
        
        try:
            response = requests.delete(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to delete table: {str(e)}")
            return None

    def batch_delete_tables(self, app_token: str, table_ids: List[str]) -> Optional[Dict]:
        """批量删除数据表
        
        Args:
            app_token: 多维表格的应用token
            table_ids: 要删除的表格ID列表
            
        Returns:
            Dict: 成功返回删除结果，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/batch_delete"
        payload = {
            "table_ids": table_ids
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to batch delete tables: {str(e)}")
            return None

    def get_records(self, 
                   app_token: str, 
                   table_id: str, 
                   view_id: Optional[str] = None,
                   page_size: int = 20,
                   page_token: Optional[str] = None) -> Optional[Dict]:
        """获取记录列表
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            view_id: 视图ID（可选）
            page_size: 分页大小，默认20，最大100
            page_token: 分页标记，第一次请求不填
            
        Returns:
            Dict: 成功返回记录列表，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        params = {
            "page_size": min(page_size, 100)  # 确保不超过最大限制
        }
        if view_id:
            params["view_id"] = view_id
        if page_token:
            params["page_token"] = page_token
            
        try:
            response = requests.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get records: {str(e)}")
            return None

    def get_record(self, app_token: str, table_id: str, record_id: str) -> Optional[Dict]:
        """获取单条记录
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            record_id: 记录ID
            
        Returns:
            Dict: 成功返回记录信息，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        
        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get record: {str(e)}")
            return None

    def filter_records(self, 
                      app_token: str, 
                      table_id: str, 
                      view_id: Optional[str] = None,
                      field_names: Optional[List[str]] = None,
                      filter_conditions: Optional[Dict] = None,
                      sort: Optional[List[Dict]] = None,
                      page_size: int = 20,
                      page_token: Optional[str] = None) -> Optional[Dict]:
        """根据条件筛选记录
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            view_id: 视图ID（可选）
            field_names: 要返回的字段名列表（可选）
            filter_conditions: 过滤条件（可选）
            sort: 排序条件（可选）
            page_size: 分页大小，默认20，最大100
            page_token: 分页标记，第一次请求不填
            
        Returns:
            Dict: 成功返回记录列表，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/search"
        
        payload = {
            "page_size": min(page_size, 100)
        }
        
        if view_id:
            payload["view_id"] = view_id
        if field_names:
            payload["field_names"] = field_names
        if filter_conditions:
            payload["filter"] = filter_conditions
        if sort:
            payload["sort"] = sort
        if page_token:
            payload["page_token"] = page_token
            
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to filter records: {str(e)}")
            return None

    def create_records(self, app_token: str, table_id: str, records: List[Dict], user_id_type: str = "user_id") -> Optional[Dict]:
        """批量创建记录
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            records: 记录列表，每条记录必须包含fields字段
            user_id_type: 用户ID类型，可选值：user_id（用户ID）/open_id（应用ID）/union_id（企业ID）/email（邮箱）
            
        Returns:
            Dict: 成功返回创建的记录列表，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
        
        # 确保每批次不超过500条记录
        batch_size = 500
        total_records = len(records)
        results = []
        
        for i in range(0, total_records, batch_size):
            batch = records[i:i + batch_size]
            payload = {
                "records": batch,
                "user_id_type": user_id_type
            }
            
            try:
                response = requests.post(url, headers=self._get_headers(), json=payload)
                response.raise_for_status()
                result = response.json()
                if result.get('code') == 0:
                    results.extend(result.get('data', {}).get('records', []))
                else:
                    logger.error(f"Failed to create records batch {i//batch_size + 1}: {result}")
                    return None
            except Exception as e:
                logger.error(f"Failed to create records batch {i//batch_size + 1}: {str(e)}")
                return None
                
            # 添加延迟避免触发频率限制
            if i + batch_size < total_records:
                time.sleep(0.1)  # 100ms延迟
                
        return {"code": 0, "data": {"records": results}}

    def update_records(self, app_token: str, table_id: str, records: List[Dict], user_id_type: str = "user_id") -> Optional[Dict]:
        """批量更新记录
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            records: 记录列表，每条记录必须包含record_id和fields字段
            user_id_type: 用户ID类型，可选值：user_id（用户ID）/open_id（应用ID）/union_id（企业ID）/email（邮箱）
            
        Returns:
            Dict: 成功返回更新的记录列表，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update"
        
        # 确保每批次不超过500条记录
        batch_size = 500
        total_records = len(records)
        results = []
        
        for i in range(0, total_records, batch_size):
            batch = records[i:i + batch_size]
            payload = {
                "records": batch,
                "user_id_type": user_id_type
            }
            
            try:
                response = requests.post(url, headers=self._get_headers(), json=payload)
                response.raise_for_status()
                result = response.json()
                if result.get('code') == 0:
                    results.extend(result.get('data', {}).get('records', []))
                else:
                    logger.error(f"Failed to update records batch {i//batch_size + 1}: {result}")
                    return None
            except Exception as e:
                logger.error(f"Failed to update records batch {i//batch_size + 1}: {str(e)}")
                return None
                
            # 添加延迟避免触发频率限制
            if i + batch_size < total_records:
                time.sleep(0.1)  # 100ms延迟
                
        return {"code": 0, "data": {"records": results}}

    def delete_records(self, app_token: str, table_id: str, record_ids: List[str]) -> Optional[Dict]:
        """批量删除记录
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            record_ids: 记录ID列表
            
        Returns:
            Dict: 成功返回删除结果，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete"
        
        # 确保每批次不超过500条记录
        batch_size = 500
        total_records = len(record_ids)
        deleted_record_ids = []
        
        for i in range(0, total_records, batch_size):
            batch = record_ids[i:i + batch_size]
            payload = {
                "records": batch
            }
            
            try:
                response = requests.post(url, headers=self._get_headers(), json=payload)
                response.raise_for_status()
                result = response.json()
                if result.get('code') == 0:
                    deleted_record_ids.extend(batch)
                else:
                    logger.error(f"Failed to delete records batch {i//batch_size + 1}: {result}")
                    return None
            except Exception as e:
                logger.error(f"Failed to delete records batch {i//batch_size + 1}: {str(e)}")
                return None
                
            # 添加延迟避免触发频率限制
            if i + batch_size < total_records:
                time.sleep(0.1)  # 100ms延迟
                
        return {"code": 0, "data": {"records": deleted_record_ids}}

    def list_views(self, app_token: str, table_id: str, page_size: int = 20, page_token: Optional[str] = None) -> Optional[Dict]:
        """列出数据表中的所有视图
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            page_size: 分页大小，默认20，最大100
            page_token: 分页标记，第一次请求不填
            
        Returns:
            Dict: 成功返回视图列表，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/views"
        params = {
            "page_size": min(page_size, 100)
        }
        if page_token:
            params["page_token"] = page_token
            
        try:
            response = requests.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to list views: {str(e)}")
            return None

    def create_view(self, app_token: str, table_id: str, view_name: str, view_type: str = "grid") -> Optional[Dict]:
        """创建视图
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            view_name: 视图名称
            view_type: 视图类型，默认为grid（网格视图）
            
        Returns:
            Dict: 成功返回视图信息，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/views"
        
        payload = {
            "view_name": view_name,
            "view_type": view_type
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to create view: {str(e)}")
            return None

    def delete_view(self, app_token: str, table_id: str, view_id: str) -> Optional[Dict]:
        """删除视图
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            view_id: 视图ID
            
        Returns:
            Dict: 成功返回删除结果，失败返回None
        """
        if not self._ensure_token():
            return None
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/views/{view_id}"
        
        try:
            response = requests.delete(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to delete view: {str(e)}")
            return None

    def upload_file_to_bitable(self, app_token: str, table_id: str, file_path: str, file_token: Optional[str] = None) -> Optional[Dict]:
        """上传文件到多维表格
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            file_path: 本地文件路径
            file_token: 文件token（可选，如果已经上传到云空间）
            
        Returns:
            Dict: 成功返回文件信息，失败返回None
        """
        if not self._ensure_token():
            return None
            
        # 如果没有提供file_token，先上传文件到云空间
        if not file_token:
            try:
                with open(file_path, 'rb') as f:
                    result = self.upload_file(f, os.path.basename(file_path))
                    if not result or result.get('code') != 0:
                        logger.error(f"Failed to upload file to cloud: {result}")
                        return None
                    file_token = result.get('data', {}).get('file_token')
            except Exception as e:
                logger.error(f"Failed to read file {file_path}: {str(e)}")
                return None
                
        # 将文件添加到多维表格
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/attachments"
        payload = {
            "file_token": file_token
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to add file to bitable: {str(e)}")
            return None

    def batch_upload_files(self, app_token: str, table_id: str, file_paths: List[str]) -> List[Dict]:
        """批量上传文件到多维表格
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            file_paths: 本地文件路径列表
            
        Returns:
            List[Dict]: 上传结果列表，每个元素包含文件信息或None（如果上传失败）
        """
        results = []
        for file_path in file_paths:
            result = self.upload_file_to_bitable(app_token, table_id, file_path)
            results.append(result)
            if result:  # 成功上传后添加延迟
                time.sleep(0.1)  # 100ms延迟
        return results

    def download_attachment(self, app_token: str, table_id: str, file_token: str, save_path: str) -> bool:
        """下载多维表格中的附件
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            file_token: 文件token
            save_path: 保存路径
            
        Returns:
            bool: 下载成功返回True，失败返回False
        """
        if not self._ensure_token():
            return False
            
        url = f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/attachments/{file_token}/download"
        
        try:
            response = requests.get(url, headers=self._get_headers(), stream=True)
            response.raise_for_status()
            
            # 获取下载URL
            download_url = response.json().get('data', {}).get('download_url')
            if not download_url:
                logger.error("Failed to get download URL")
                return False
                
            # 下载文件
            response = requests.get(download_url, stream=True)
            response.raise_for_status()
            
            # 保存文件
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        
            return True
            
        except Exception as e:
            logger.error(f"Failed to download attachment: {str(e)}")
            return False

    def batch_download_attachments(self, app_token: str, table_id: str, downloads: List[Dict[str, str]]) -> List[bool]:
        """批量下载多维表格中的附件
        
        Args:
            app_token: 多维表格的应用token
            table_id: 表格ID
            downloads: 下载信息列表，每个元素是包含file_token和save_path的字典
            
        Returns:
            List[bool]: 下载结果列表，True表示成功，False表示失败
        """
        results = []
        for download in downloads:
            file_token = download.get('file_token')
            save_path = download.get('save_path')
            if not file_token or not save_path:
                logger.error("Missing file_token or save_path")
                results.append(False)
                continue
                
            result = self.download_attachment(app_token, table_id, file_token, save_path)
            results.append(result)
            if result:  # 成功下载后添加延迟
                time.sleep(0.1)  # 100ms延迟
        return results

def date_to_timestamp(date_str: str) -> int:
    """将日期字符串转换为时间戳（毫秒）
    Args:
        date_str: 日期字符串，格式为YYYY-MM-DD
    Returns:
        int: 时间戳（毫秒）
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return int(dt.timestamp() * 1000)
    except Exception as e:
        logger.error(f"Failed to convert date {date_str}: {str(e)}")
        return 0 