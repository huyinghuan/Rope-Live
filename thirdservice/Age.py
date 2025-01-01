# -*- coding: utf-8 -*-
from aip import AipFace
import json
import argparse
import base64
import os
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.ft.v20200304 import ft_client, models
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
config = {}

# 读取config.json文件
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

def tencentChangeAge(image, name):

    # 为了保护密钥安全，建议将密钥设置在环境变量中或者配置文件中，请参考本文凭证管理章节。
    # 硬编码密钥到代码中有可能随代码泄露而暴露，有安全隐患，并不推荐。
    # cred = credential.Credential("secretId", "secretKey")
    txConf = config["tencent"]
    cred = credential.Credential(
        txConf["SECRET_ID"],
        txConf["SECRET_KEY"])
    
    httpProfile = HttpProfile()
    httpProfile.endpoint = "ft.tencentcloudapi.com"
    

    # 实例化一个client选项，可选的，没有特殊需求可以跳过
    clientProfile = ClientProfile()
    clientProfile.httpProfile = httpProfile
    # 实例化要请求产品的client对象,clientProfile是可选的
    client = ft_client.FtClient(cred, "ap-guangzhou", clientProfile)

    for i in config['age_list']:
        # 实例化一个请求对象,每个接口都会对应一个request对象
        req = models.ChangeAgePicRequest()
        with open(image, 'rb') as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            params = {
                "Image": image_base64,
                "AgeInfos":[{
                    "Age": i
                }]
            }
            req.from_json_string(json.dumps(params))
            # 返回的resp是一个ChangeAgePicResponse的实例，与请求对象对应
            resp = client.ChangeAgePic(req)
            if hasattr(resp,'ResultImage'):
                with open("dist/"+ name + '/' + name + '_' + str(i) + '-tx.jpg', 'wb') as f:
                    f.write(base64.b64decode(resp.ResultImage))


def baiduChangeAge(image, name):
    baiduConfig = config["baidu"]
    APP_ID = baiduConfig['appId']
    API_KEY = baiduConfig['apiKey']
    SECRET_KEY = baiduConfig['secretKey']
    client = AipFace(APP_ID, API_KEY, SECRET_KEY)
    """ 调用人脸年龄识别 """
    # 调用人脸年龄识别
    for i in config['age_list']:
        options = {}
        options["target"] = i
        with open(image, 'rb') as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            try:
                # TO_OLD V2_AGE
                response = client.faceSkinSmoothV1(image=image_base64, image_type="BASE64", action_type="TO_OLD", options=options)
                if 'error_code' in response:
                    if response['error_code'] == 0:
                        image_change = response["result"]['image']
                        with open("dist/"+ name + '/' + name + '_' + str(i) + '.jpg', 'wb') as f:
                            f.write(base64.b64decode(image_change))
            except Exception as e:
                print(e)
                return
    return


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Age detection using AipFace')
    parser.add_argument('image', type=str, help='Path to the image file')
    parser.add_argument('--name', type=str, default='test', help='指定输出文件名,输出路径为name/name_$age.jpg')
    args = parser.parse_args()
    
    # 判断路径是否为文件夹
    if os.path.isdir(args.image):
        # 遍历文件夹下所有文件
        for root, dirs, files in os.walk(args.image):
            for file in files:
                image = os.path.join(root, file)
                # 获取文件名
                name = os.path.splitext(file)[0]
                # 创建同名文件夹
                os.makedirs("dist/"+name, exist_ok=True)
                tencentChangeAge(image, name)
    else:
        # 创建同名文件夹
        os.makedirs("dist/"+args.name, exist_ok=True)
        #baiduChangeAge(args.image, args.name)
        tencentChangeAge(args.image, args.name)