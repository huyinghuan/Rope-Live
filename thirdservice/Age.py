from aip import AipFace
import json
import argparse
import base64
import os

config = {}

# 读取config.json文件
with open('config.json', 'r') as config_file:
    config = json.load(config_file)




def baiduChangeAge(image, name):
    baiduConfig = config["baidu"]
    APP_ID = baiduConfig['appId']
    API_KEY = baiduConfig['apiKey']
    SECRET_KEY = baiduConfig['secretKey']
    client = AipFace(APP_ID, API_KEY, SECRET_KEY)
    """ 调用人脸年龄识别 """
    os.makedirs("dist/"+name, exist_ok=True)
 

    # 调用人脸年龄识别
    for i in config['age_list']:
        options = {}
        options["target"] = i
        with open(image, 'rb') as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            try:
                response = client.faceSkinSmoothV1(image=image_base64, image_type="BASE64", action_type="V2_AGE", options=options)
                if 'error_code' in response:
                    if response['error_code'] == 0:
                        image_change = response["result"]['image']
                        # 创建同名文件夹
                        # 创建同名文件夹
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
    baiduChangeAge(args.image, args.name)