import cv2
import math
from math import sin, cos, acos, degrees
import numpy as np
from skimage import transform as trans
import torch
import torchvision
torchvision.disable_beta_transforms_warning()
from torchvision.transforms import v2
from numpy.linalg import norm as l2norm

# <--left profile
src1 = np.array([[51.642, 50.115], [57.617, 49.990], [35.740, 69.007],
                 [51.157, 89.050], [57.025, 89.702]],
                dtype=np.float32)

# <--left
src2 = np.array([[45.031, 50.118], [65.568, 50.872], [39.677, 68.111],
                 [45.177, 86.190], [64.246, 86.758]],
                dtype=np.float32)

# ---frontal
src3 = np.array([[39.730, 51.138], [72.270, 51.138], [56.000, 68.493],
                 [42.463, 87.010], [69.537, 87.010]],
                dtype=np.float32)

# -->right
src4 = np.array([[46.845, 50.872], [67.382, 50.118], [72.737, 68.111],
                 [48.167, 86.758], [67.236, 86.190]],
                dtype=np.float32)

# -->right profile
src5 = np.array([[54.796, 49.990], [60.771, 50.115], [76.673, 69.007],
                 [55.388, 89.702], [61.257, 89.050]],
                dtype=np.float32)

src = np.array([src1, src2, src3, src4, src5])
src_map = {112: src, 224: src * 2}

arcface_src = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
     [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float32)

arcface_src = np.expand_dims(arcface_src, axis=0)

def pad_image_by_size(img, image_size):
    # Se image_size non è una tupla, crea una tupla con altezza e larghezza uguali
    if not isinstance(image_size, tuple):
        image_size = (image_size, image_size)

    # Larghezza e altezza dell'immagine
    w, h = img.size(dim=2), img.size(dim=1)

    # Dimensioni target
    target_h, target_w = image_size

    # Verifica se la larghezza o l'altezza è inferiore alle dimensioni target
    if w < target_w or h < target_h:
        # Calcolo del padding necessario a destra e in basso
        pad_right = max(target_w - w, 0)  # Assicura che il padding sia non negativo
        pad_bottom = max(target_h - h, 0)  # Assicura che il padding sia non negativo

        # Aggiungi padding all'immagine (pad_left, pad_right, pad_top, pad_bottom)
        img = torch.nn.functional.pad(img, (0, pad_right, 0, pad_bottom), mode='constant', value=0)

    return img

def transform(img, center, output_size, scale, rotation):
    # pad image by image size
    img = pad_image_by_size(img, output_size)

    scale_ratio = scale
    rot = float(rotation) * np.pi / 180.0
    t1 = trans.SimilarityTransform(scale=scale_ratio)
    cx = center[0] * scale_ratio
    cy = center[1] * scale_ratio
    t2 = trans.SimilarityTransform(translation=(-1 * cx, -1 * cy))
    t3 = trans.SimilarityTransform(rotation=rot)
    t4 = trans.SimilarityTransform(translation=(output_size / 2,
                                                output_size / 2))
    t = t1 + t2 + t3 + t4
    M = t.params[0:2]

    cropped = v2.functional.affine(img, np.rad2deg(t.rotation), (t.translation[0], t.translation[1]) , t.scale, 0, interpolation=v2.InterpolationMode.BILINEAR, center = (0,0) )
    cropped = v2.functional.crop(cropped, 0,0, output_size, output_size)

    return cropped, M

def trans_points2d(pts, M):
    # Add a column of ones to the pts array to create homogeneous coordinates
    ones_column = np.ones((pts.shape[0], 1), dtype=np.float32)
    homogeneous_pts = np.hstack([pts, ones_column])

    # Perform the matrix multiplication for all points at once
    transformed_pts = np.dot(homogeneous_pts, M.T)

    # Return only the first two columns (x and y coordinates)
    return transformed_pts[:, :2]

'''
def trans_points2d(pts, M):
    new_pts = np.zeros(shape=pts.shape, dtype=np.float32)
    for i in range(pts.shape[0]):
        pt = pts[i]
        new_pt = np.array([pt[0], pt[1], 1.], dtype=np.float32)
        new_pt = np.dot(M, new_pt)
        #print('new_pt', new_pt.shape, new_pt)
        new_pts[i] = new_pt[0:2]

    return new_pts
'''

def trans_points3d(pts, M):
    scale = np.sqrt(M[0, 0]**2 + M[0, 1]**2)

    # Add a column of ones to the pts array to create homogeneous coordinates for 2D transformation
    ones_column = np.ones((pts.shape[0], 1), dtype=np.float32)
    homogeneous_pts = np.hstack([pts[:, :2], ones_column])

    # Perform the matrix multiplication for all points at once
    transformed_2d = np.dot(homogeneous_pts, M.T)

    # Scale the z-coordinate
    scaled_z = pts[:, 2] * scale

    # Combine the transformed 2D points with the scaled z-coordinate
    transformed_pts = np.hstack([transformed_2d[:, :2], scaled_z.reshape(-1, 1)])

    return transformed_pts

'''
def trans_points3d(pts, M):
    scale = np.sqrt(M[0][0] * M[0][0] + M[0][1] * M[0][1])
    new_pts = np.zeros(shape=pts.shape, dtype=np.float32)
    for i in range(pts.shape[0]):
        pt = pts[i]
        new_pt = np.array([pt[0], pt[1], 1.], dtype=np.float32)
        new_pt = np.dot(M, new_pt)
        #print('new_pt', new_pt.shape, new_pt)
        new_pts[i][0:2] = new_pt[0:2]
        new_pts[i][2] = pts[i][2] * scale

    return new_pts
'''

def trans_points(pts, M):
    if pts.shape[1] == 2:
        return trans_points2d(pts, M)
    else:
        return trans_points3d(pts, M)

def estimate_affine_matrix_3d23d(X, Y):
    ''' Using least-squares solution
    Args:
        X: [n, 3]. 3d points(fixed)
        Y: [n, 3]. corresponding 3d points(moving). Y = PX
    Returns:
        P_Affine: (3, 4). Affine camera matrix (the third row is [0, 0, 0, 1]).
    '''
    X_homo = np.hstack((X, np.ones([X.shape[0],1]))) #n x 4
    P = np.linalg.lstsq(X_homo, Y,rcond=None)[0].T # Affine matrix. 3 x 4
    return P

def P2sRt(P):
    ''' decompositing camera matrix P
    Args:
        P: (3, 4). Affine Camera Matrix.
    Returns:
        s: scale factor.
        R: (3, 3). rotation matrix.
        t: (3,). translation.
    '''
    t = P[:, 3]
    R1 = P[0:1, :3]
    R2 = P[1:2, :3]
    s = (np.linalg.norm(R1) + np.linalg.norm(R2))/2.0
    r1 = R1/np.linalg.norm(R1)
    r2 = R2/np.linalg.norm(R2)
    r3 = np.cross(r1, r2)

    R = np.concatenate((r1, r2, r3), 0)
    return s, R, t

def matrix2angle(R):
    ''' get three Euler angles from Rotation Matrix
    Args:
        R: (3,3). rotation matrix
    Returns:
        x: pitch
        y: yaw
        z: roll
    '''
    sy = math.sqrt(R[0,0] * R[0,0] +  R[1,0] * R[1,0])

    singular = sy < 1e-6

    if  not singular :
        x = math.atan2(R[2,1] , R[2,2])
        y = math.atan2(-R[2,0], sy)
        z = math.atan2(R[1,0], R[0,0])
    else :
        x = math.atan2(-R[1,2], R[1,1])
        y = math.atan2(-R[2,0], sy)
        z = 0

    # rx, ry, rz = np.rad2deg(x), np.rad2deg(y), np.rad2deg(z)
    rx, ry, rz = x*180/np.pi, y*180/np.pi, z*180/np.pi
    return rx, ry, rz

def warp_affine_torchvision(img, matrix, image_size, rotation_ratio=0.0, border_value=0.0, border_mode='replicate', interpolation_value=v2.functional.InterpolationMode.NEAREST, device='cpu'):
    # Ensure image_size is a tuple (width, height)
    if isinstance(image_size, int):
        image_size = (image_size, image_size)

    # Ensure the image tensor is on the correct device and of type float
    if isinstance(img, torch.Tensor):
        img_tensor = img.to(device).float()
        if img_tensor.dim() == 3:  # If no batch dimension, add one
            img_tensor = img_tensor.unsqueeze(0)
    else:
        img_tensor = torch.from_numpy(img).unsqueeze(0).permute(0, 3, 1, 2).float().to(device)

    # Extract the translation parameters from the affine matrix
    t = trans.SimilarityTransform()
    t.params[0:2] = matrix

    # Define default rotation
    rotation = t.rotation

    if rotation_ratio != 0:
        rotation *=rotation_ratio  # Rotation in degrees

    # Convert border mode
    if border_mode == 'replicate':
        fill = [border_value] * img_tensor.shape[1]  # Same value for all channels
    elif border_mode == 'constant':
        fill = [border_value] * img_tensor.shape[1]  # Same value for all channels
    else:
        raise ValueError("Unsupported border_mode. Use 'replicate' or 'constant'.")

    # Apply the affine transformation
    warped_img_tensor = v2.functional.affine(img_tensor, angle=rotation, translate=(t.translation[0], t.translation[1]), scale=t.scale, shear=(0.0, 0.0), interpolation=interpolation_value, center=(0, 0), fill=fill)

    # Crop the image to the desired size
    warped_img_tensor = v2.functional.crop(warped_img_tensor, 0,0, image_size[1], image_size[0])

    return warped_img_tensor.squeeze(0)

def umeyama(src, dst, estimate_scale):
    num = src.shape[0]
    dim = src.shape[1]
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_demean = src - src_mean
    dst_demean = dst - dst_mean
    A = np.dot(dst_demean.T, src_demean) / num
    d = np.ones((dim,), dtype=np.double)
    if np.linalg.det(A) < 0:
        d[dim - 1] = -1
    T = np.eye(dim + 1, dtype=np.double)
    U, S, V = np.linalg.svd(A)
    rank = np.linalg.matrix_rank(A)
    if rank == 0:
        return np.nan * T
    elif rank == dim - 1:
        if np.linalg.det(U) * np.linalg.det(V) > 0:
            T[:dim, :dim] = np.dot(U, V)
        else:
            s = d[dim - 1]
            d[dim - 1] = -1
            T[:dim, :dim] = np.dot(U, np.dot(np.diag(d), V))
            d[dim - 1] = s
    else:
        T[:dim, :dim] = np.dot(U, np.dot(np.diag(d), V.T))
    if estimate_scale:
        scale = 1.0 / src_demean.var(axis=0).sum() * np.dot(S, d)
    else:
        scale = 1.0
    T[:dim, dim] = dst_mean - scale * np.dot(T[:dim, :dim], src_mean.T)
    T[:dim, :dim] *= scale
    return T

def get_matrix(lmk, templates):
    if templates.shape[0] == 1:
        return umeyama(lmk, templates[0], True)[0:2, :]
    test_lmk = np.insert(lmk, 2, values=np.ones(5), axis=1)
    min_error, best_matrix = float("inf"), []
    for i in np.arange(templates.shape[0]):
        matrix = umeyama(lmk, templates[i], True)[0:2, :]
        error = np.sum(
            np.sqrt(np.sum((np.dot(matrix, test_lmk.T).T - templates[i]) ** 2, axis=1))
        )
        if error < min_error:
            min_error, best_matrix = error, matrix
    return best_matrix

def align_crop(img, lmk, image_size, mode='arcfacemap', interpolation=v2.InterpolationMode.NEAREST):
    if mode != 'arcfacemap':
        if mode == 'arcface112':
            templates = float(image_size) / 112.0 * arcface_src
        else:
            factor = float(image_size) / 128.0
            templates = arcface_src * factor
            templates[:, 0] += (factor * 8.0)
    else:
        templates = float(image_size) / 112.0 * src_map[112]

    matrix = get_matrix(lmk, templates)
    '''
    warped = cv2.warpAffine(
        img,
        matrix,
        (image_size, image_size),
        borderValue=0.0,
        borderMode=cv2.BORDER_REPLICATE,
    )
    '''
    warped = warp_affine_torchvision(img, matrix, (image_size, image_size), rotation_ratio=57.2958, border_value=0.0, border_mode='replicate', interpolation_value=v2.functional.InterpolationMode.NEAREST, device='cuda')

    return warped, matrix

def get_arcface_template(image_size=112, mode='arcface112'):
    if mode=='arcface112':
        template = float(image_size) / 112.0 * arcface_src
    elif mode=='arcface128':
        factor = float(image_size) / 128.0
        template = arcface_src * factor
        template[:, 0] += (factor * 8.0)
    else:
        template = float(image_size) / 112.0 * src_map[112]

    return template

# lmk is prediction; src is template
def estimate_norm_arcface_template(lmk, src=arcface_src):
    assert lmk.shape == (5, 2)
    tform = trans.SimilarityTransform()
    lmk_tran = np.insert(lmk, 2, values=np.ones(5), axis=1)
    min_M = []
    min_index = []
    min_error = float('inf')

    for i in np.arange(src.shape[0]):
        tform.estimate(lmk, src[i])
        M = tform.params[0:2, :]
        results = np.dot(M, lmk_tran.T)
        results = results.T
        error = np.sum(np.sqrt(np.sum((results - src[i])**2, axis=1)))
        #print((error, min_error))
        if error < min_error:
            min_error = error
            min_M = M
            min_index = i
    #print(src[min_index])
    return min_M, min_index

# lmk is prediction; src is template
def estimate_norm(lmk, image_size=112, mode='arcface112'):
    assert lmk.shape == (5, 2)
    tform = trans.SimilarityTransform()
    lmk_tran = np.insert(lmk, 2, values=np.ones(5), axis=1)
    min_M = []
    min_index = []
    min_error = float('inf')

    if mode != 'arcfacemap':
        if mode == 'arcface112':
            src = float(image_size) / 112.0 * arcface_src
        else:
            factor = float(image_size) / 128.0
            src = arcface_src * factor
            src[:, 0] += (factor * 8.0)
    else:
        src = float(image_size) / 112.0 * src_map[112]

    for i in np.arange(src.shape[0]):
        tform.estimate(lmk, src[i])
        M = tform.params[0:2, :]
        results = np.dot(M, lmk_tran.T)
        results = results.T
        error = np.sum(np.sqrt(np.sum((results - src[i])**2, axis=1)))
        #print((error, min_error))
        if error < min_error:
            min_error = error
            min_M = M
            min_index = i
    #print(src[min_index])
    return min_M, min_index

def warp_face_by_bounding_box(img, bboxes, image_size=112):
    # pad image by image size
    img = pad_image_by_size(img, image_size)

    # Set source points from bounding boxes
    source_points = np.array([ [ bboxes[0], bboxes[1] ], [ bboxes[2], bboxes[1] ], [ bboxes[0], bboxes[3] ], [ bboxes[2], bboxes[3] ] ]).astype(np.float32)

    # Set target points from image size
    target_points = np.array([ [ 0, 0 ], [ image_size, 0 ], [ 0, image_size ], [ image_size, image_size ] ]).astype(np.float32)

    # Find transform
    tform = trans.SimilarityTransform()
    tform.estimate(source_points, target_points)

    # Transform
    img = v2.functional.affine(img, tform.rotation, (tform.translation[0], tform.translation[1]) , tform.scale, 0, interpolation=v2.InterpolationMode.BILINEAR, center = (0,0) )
    img = v2.functional.crop(img, 0,0, image_size, image_size)
    M = tform.params[0:2]

    return img, M

def warp_face_by_face_landmark_5(img, kpss, image_size=112, mode='arcface112', interpolation=v2.InterpolationMode.NEAREST):
    # pad image by image size
    img = pad_image_by_size(img, image_size)

    M, pose_index = estimate_norm(kpss, image_size, mode=mode)
    t = trans.SimilarityTransform()
    t.params[0:2] = M
    img = v2.functional.affine(img, t.rotation*57.2958, (t.translation[0], t.translation[1]) , t.scale, 0, interpolation=interpolation, center = (0, 0) )
    img = v2.functional.crop(img, 0,0, image_size, image_size)

    return img, M

def getRotationMatrix2D(center, output_size, scale, rotation, is_clockwise = True):
    scale_ratio = scale
    if not is_clockwise:
        rotation = -rotation
    rot = float(rotation) * np.pi / 180.0
    t1 = trans.SimilarityTransform(scale=scale_ratio)
    cx = center[0] * scale_ratio
    cy = center[1] * scale_ratio
    t2 = trans.SimilarityTransform(translation=(-1 * cx, -1 * cy))
    t3 = trans.SimilarityTransform(rotation=rot)
    t4 = trans.SimilarityTransform(translation=(output_size / 2,
                                                output_size / 2))
    t = t1 + t2 + t3 + t4
    M = t.params[0:2]

    return M

def invertAffineTransform(M):
    '''
    t = trans.SimilarityTransform()
    t.params[0:2] = M
    IM = t.inverse.params[0:2, :]
    '''
    M_H = np.vstack([M, np.array([0, 0, 1])])
    IM = np.linalg.inv(M_H)

    return IM

def warp_face_by_bounding_box_for_landmark_68(img, bbox, input_size):
    """
    :param img: raw image
    :param bbox: the bbox for the face
    :param input_size: tuple input image size
    :return:
    """
    # pad image by image size
    img = pad_image_by_size(img, input_size[0])

    scale = 195 / np.subtract(bbox[2:], bbox[:2]).max()
    translation = (256 - np.add(bbox[2:], bbox[:2]) * scale) * 0.5
    rotation = 0

    t1 = trans.SimilarityTransform(scale=scale)
    t2 = trans.SimilarityTransform(rotation=rotation)
    t3 = trans.SimilarityTransform(translation=translation)

    t = t1 + t2 + t3
    affine_matrix = np.array([ [ scale, 0, translation[0] ], [ 0, scale, translation[1] ] ])

    crop_image = v2.functional.affine(img, t.rotation, (t.translation[0], t.translation[1]) , t.scale, 0, interpolation=v2.InterpolationMode.BILINEAR, center = (0,0) )
    crop_image = v2.functional.crop(crop_image, 0,0, input_size[1], input_size[0])

    if torch.mean(crop_image.to(dtype=torch.float32)[0, :, :]) < 30:
        crop_image = cv2.cvtColor(crop_image.permute(1, 2, 0).to('cpu').numpy(), cv2.COLOR_RGB2Lab)
        crop_image[:, :, 0] = cv2.createCLAHE(clipLimit = 2).apply(crop_image[:, :, 0])
        crop_image = torch.from_numpy(cv2.cvtColor(crop_image, cv2.COLOR_Lab2RGB)).to('cuda').permute(2, 0, 1)

    return crop_image, affine_matrix

def warp_face_by_bounding_box_for_landmark_98(img, bbox_org, input_size):
    """
    :param img: raw image
    :param bbox: the bbox for the face
    :param input_size: tuple input image size
    :return:
    """
    # pad image by image size
    img = pad_image_by_size(img, input_size[0])

    ##preprocess
    bbox = bbox_org.copy()
    min_face = 20
    base_extend_range = [0.2, 0.3]
    bbox_width = bbox[2] - bbox[0]
    bbox_height = bbox[3] - bbox[1]
    if bbox_width <= min_face or bbox_height <= min_face:
        return None, None
    add = int(max(bbox_width, bbox_height))

    bimg = torch.nn.functional.pad(img, (add, add, add, add), 'constant', 0)

    bbox += add

    face_width = (1 + 2 * base_extend_range[0]) * bbox_width
    center = [(bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2]

    ### make the box as square
    bbox[0] = center[0] - face_width // 2
    bbox[1] = center[1] - face_width // 2
    bbox[2] = center[0] + face_width // 2
    bbox[3] = center[1] + face_width // 2

    # crop
    bbox = bbox.astype(np.int32)
    crop_image = bimg[:, bbox[1]:bbox[3], bbox[0]:bbox[2]]

    h, w = (crop_image.size(dim=1), crop_image.size(dim=2))

    t_resize = v2.Resize((input_size[1], input_size[0]), antialias=False)
    crop_image = t_resize(crop_image)

    return crop_image, [h, w, bbox[1], bbox[0], add]

def create_bounding_box_from_face_landmark_106_98_68(face_landmark_106_98_68):
    min_x, min_y = np.min(face_landmark_106_98_68, axis = 0)
    max_x, max_y = np.max(face_landmark_106_98_68, axis = 0)
    bounding_box = np.array([ min_x, min_y, max_x, max_y ]).astype(np.int16)
    return bounding_box

def convert_face_landmark_68_to_5(face_landmark_68, face_landmark_68_score):
    lm_idx = np.array([31, 37, 40, 43, 46, 49, 55], dtype=np.int32) - 1
    face_landmark_5 = np.stack([
        np.mean(face_landmark_68[lm_idx[[1, 2]], :], 0),  # left eye
        np.mean(face_landmark_68[lm_idx[[3, 4]], :], 0),  # right eye
        face_landmark_68[lm_idx[0], :],  # nose
        face_landmark_68[lm_idx[5], :],  # lip
        face_landmark_68[lm_idx[6], :]   # lip
    ], axis=0)

    if np.any(face_landmark_68_score):
        face_landmark_5_score = np.stack([
            np.mean(face_landmark_68_score[lm_idx[[1, 2]], :], 0),  # left eye
            np.mean(face_landmark_68_score[lm_idx[[3, 4]], :], 0),  # right eye
            face_landmark_68_score[lm_idx[0], :],  # nose
            face_landmark_68_score[lm_idx[5], :],  # lip
            face_landmark_68_score[lm_idx[6], :]   # lip
        ], axis=0)
    else:
        face_landmark_5_score = np.array([])

    return face_landmark_5, face_landmark_5_score

def convert_face_landmark_98_to_5(face_landmark_98, face_landmark_98_score):
    face_landmark_5 = np.array(
    [
        face_landmark_98[96], # eye left
        face_landmark_98[97], # eye-right
        face_landmark_98[54], # nose,
        face_landmark_98[76], # lip left
        face_landmark_98[82]  # lip right
    ])

    face_landmark_5_score = np.array(
    [
        face_landmark_98_score[96], # eye left
        face_landmark_98_score[97], # eye-right
        face_landmark_98_score[54], # nose,
        face_landmark_98_score[76], # lip left
        face_landmark_98_score[82]  # lip right
    ])

    return face_landmark_5, face_landmark_5_score

def convert_face_landmark_106_to_5(face_landmark_106):
    face_landmark_5 = np.array(
    [
        face_landmark_106[38], # eye left
        face_landmark_106[88], # eye-right
        face_landmark_106[86], # nose,
        face_landmark_106[52], # lip left
        face_landmark_106[61]  # lip right
    ])

    return face_landmark_5

def convert_face_landmark_203_to_5(face_landmark_203, use_mean_eyes=False):
    if use_mean_eyes:
        eye_left = np.mean(face_landmark_203[[0, 6, 12, 18]], axis=0)  # Average of left eye points
        eye_right = np.mean(face_landmark_203[[24, 30, 36, 42]], axis=0)  # Average of right eye points
    else:
        eye_left = face_landmark_203[197]  # Specific left eye point
        eye_right = face_landmark_203[198]  # Specific right eye point

    nose = face_landmark_203[201]  # Nose
    lip_left = face_landmark_203[48]  # Left lip corner
    lip_right = face_landmark_203[66]  # Right lip corner

    face_landmark_5 = np.array([eye_left, eye_right, nose, lip_left, lip_right])

    return face_landmark_5

def convert_face_landmark_478_to_5(face_landmark_478, use_mean_eyes=False):
    if use_mean_eyes:
        eye_left = np.mean(face_landmark_478[[472, 471, 470, 469]], axis=0)  # Average of left eye points
        eye_right = np.mean(face_landmark_478[[477, 476, 475, 474]], axis=0)  # Average of right eye points
    else:
        eye_left = face_landmark_478[468]  # Specific left eye point
        eye_right = face_landmark_478[473]  # Specific right eye point

    nose = face_landmark_478[4]  # Nose
    lip_left = face_landmark_478[61]  # Left lip corner
    lip_right = face_landmark_478[291]  # Right lip corner

    face_landmark_5 = np.array([eye_left, eye_right, nose, lip_left, lip_right])

    return face_landmark_5

def convert_face_landmark_x_to_5(pts, **kwargs):
    pts_score = kwargs.get('pts_score', [])
    use_mean_eyes = kwargs.get('use_mean_eyes', False)

    if pts.shape[0] == 5:
        return pts
    elif pts.shape[0] == 68:
        pt5 = convert_face_landmark_68_to_5(face_landmark_68=pts, face_landmark_68_score=pts_score)
    elif pts.shape[0] == 98:
        pt5 = convert_face_landmark_98_to_5(face_landmark_98=pts, face_landmark_98_score=pts_score)
    elif pts.shape[0] == 106:
        pt5 = convert_face_landmark_106_to_5(face_landmark_106=pts)
    elif pts.shape[0] == 203:
        pt5 = convert_face_landmark_203_to_5(face_landmark_203=pts, use_mean_eyes=use_mean_eyes)
    elif pts.shape[0] == 478:
        pt5 = convert_face_landmark_478_to_5(face_landmark_478=pts, use_mean_eyes=use_mean_eyes)
    else:
        raise Exception(f'Unknow shape: {pts.shape}')

    return pt5

def test_bbox_landmarks(img, bbox, kpss, caption='image', show_kpss_label=False):
        image = img.permute(1,2,0).to('cpu').numpy().copy()
        if len(bbox) > 0:
            box = bbox.astype(int)
            color = (255, 0, 0)
            cv2.rectangle(image, (box[0], box[1]), (box[2], box[3]), color, 2)

        if len(kpss) > 0:
            for i in range(kpss.shape[0]):
                kps = kpss[i].astype(int)
                color = (0, 0, 255)
                cv2.circle(image, (kps[0], kps[1]), 1, color,
                           2)
                if show_kpss_label:
                    if kpss.shape[0] == 5:
                        match i:
                            case 0:
                                text = "LE"
                            case 1:
                                text = "RE"
                            case 2:
                                text = "NO"
                            case 3:
                                text = "LM"
                            case 4:
                                text = "RM"
                    else:
                        text = str(i)

                    image = cv2.putText(image, text, (kps[0], kps[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2, cv2.LINE_AA, False)

        cv2.imshow(caption, image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

def test_multi_bbox_landmarks(img, bboxes, kpss, caption='image', show_kpss_label=False):
    if len(bboxes) > 0 and len(kpss) > 0:
        for i in range(np.array(kpss).shape[0]):
            test_bbox_landmarks(img, bboxes[i], kpss[i], caption=caption, show_kpss_label=show_kpss_label)
    elif len(bboxes) > 0:
        for i in range(np.array(bboxes).shape[0]):
            test_bbox_landmarks(img, bboxes[i], [], caption=caption, show_kpss_label=show_kpss_label)
    elif len(kpss) > 0:
        for i in range(np.array(kpss).shape[0]):
            test_bbox_landmarks(img, [], kpss[i], caption=caption, show_kpss_label=show_kpss_label)

def detect_img_color(img):
    frame = img.permute(1,2,0)

    b = frame[:, :, :1]
    g = frame[:, :, 1:2]
    r = frame[:, :, 2:]

    # computing the mean
    b_mean = torch.mean(b.to(float))
    g_mean = torch.mean(g.to(float))
    r_mean = torch.mean(r.to(float))

    # displaying the most prominent color
    if (b_mean > g_mean and b_mean > r_mean):
        return 'BGR'
    elif (g_mean > r_mean and g_mean > b_mean):
        return 'GBR'

    return 'RGB'

def get_face_orientation(face_size, lmk):
    assert lmk.shape == (5, 2)
    tform = trans.SimilarityTransform()
    src = np.squeeze(arcface_src, axis=0)
    src = float(face_size) / 112.0 * src
    tform.estimate(lmk, src)

    angle_deg_to_front = np.rad2deg(tform.rotation)

    return angle_deg_to_front

def rgb_to_yuv(image, normalize=False):
    """
    Convert an RGB image to YUV.
    Args:
        image (torch.Tensor): The input image tensor in RGB format (C, H, W) with values in the range [0, 255].
    Returns:
        torch.Tensor: The image tensor in YUV format (C, H, W).
    """
    if normalize:
        # Ensure the image is in the range [0, 1]
        image = torch.div(image, 255.0)

    # Define the conversion matrix from RGB to YUV
    conversion_matrix = torch.tensor([[0.299, 0.587, 0.114],
                                      [-0.14713, -0.28886, 0.436],
                                      [0.615, -0.51499, -0.10001]], device=image.device, dtype=image.dtype)

    # Apply the conversion matrix
    yuv_image = torch.tensordot(image.permute(1, 2, 0), conversion_matrix, dims=1).permute(2, 0, 1)

    return yuv_image

def yuv_to_rgb(image, normalize=False):
    """
    Convert a YUV image to RGB.
    Args:
        image (torch.Tensor): The input image tensor in YUV format (C, H, W) with values in the range [0, 1].
    Returns:
        torch.Tensor: The image tensor in RGB format (C, H, W).
    """
    # Define the conversion matrix from YUV to RGB
    conversion_matrix = torch.tensor([[1, 0, 1.13983],
                                      [1, -0.39465, -0.58060],
                                      [1, 2.03211, 0]], device=image.device, dtype=image.dtype)

    # Apply the conversion matrix
    rgb_image = torch.tensordot(image.permute(1, 2, 0), conversion_matrix, dims=1).permute(2, 0, 1)

    # Ensure the image is in the range [0, 1]
    rgb_image = torch.clamp(rgb_image, 0, 1)

    if normalize:
        rgb_image = torch.mul(rgb_image, 255.0)

    return rgb_image

def rgb_to_lab(rgb, normalize=False):
    if normalize:
        # Normalizzazione RGB a [0, 1]
        rgb = torch.div(rgb.type(torch.float32), 255.0)

    # Linearizzazione dei valori RGB
    mask = rgb > 0.04045
    rgb[mask] = torch.pow((rgb[mask] + 0.055) / 1.055, 2.4)
    rgb[~mask] = rgb[~mask] / 12.92

    # Conversione da RGB a XYZ
    matrix_rgb_to_xyz = torch.tensor([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041]
    ], dtype=rgb.dtype, device=rgb.device)

    rgb = rgb.permute(1, 2, 0).contiguous()
    xyz = torch.matmul(rgb.view(-1, 3), matrix_rgb_to_xyz.T).view(rgb.shape)

    # Normalizzazione XYZ
    white_point = torch.tensor([0.95047, 1.00000, 1.08883], dtype=xyz.dtype, device=xyz.device)
    xyz = xyz / white_point

    # Conversione da XYZ a LAB
    epsilon = 0.008856
    kappa = 903.3

    mask = xyz > epsilon
    xyz[mask] = torch.pow(xyz[mask], 1/3)
    xyz[~mask] = (kappa * xyz[~mask] + 16) / 116

    L = 116 * xyz[:, :, 1] - 16
    a = 500 * (xyz[:, :, 0] - xyz[:, :, 1])
    b = 200 * (xyz[:, :, 1] - xyz[:, :, 2])

    lab = torch.stack([L, a, b], dim=2).permute(2, 0, 1)
    return lab

def lab_to_rgb(lab, normalize=False):
    if lab.dim() != 3 or lab.shape[0] != 3:
        raise ValueError("LAB tensor must have shape (3, H, W)")

    L = lab[0, :, :]
    A = lab[1, :, :]
    B = lab[2, :, :]

    # Conversione da LAB a XYZ
    epsilon = 0.008856
    kappa = 903.3

    fy = (L + 16.0) / 116.0
    fx = A / 500.0 + fy
    fz = fy - B / 200.0

    fx3 = fx ** 3
    fz3 = fz ** 3
    x = torch.where(fx3 > epsilon, fx3, (116.0 * fx - 16.0) / kappa)
    y = torch.where(L > (kappa * epsilon), ((L + 16.0) / 116.0) ** 3, L / kappa)
    z = torch.where(fz3 > epsilon, fz3, (116.0 * fz - 16.0) / kappa)

    # White point normalization
    white_point = torch.tensor([0.95047, 1.00000, 1.08883], dtype=lab.dtype, device=lab.device)
    xyz = torch.stack([x, y, z], dim=0) * white_point[:, None, None]

    # Conversione da XYZ a RGB
    matrix_xyz_to_rgb = torch.tensor([
        [ 3.2404542, -1.5371385, -0.4985314],
        [-0.9692660,  1.8760108,  0.0415560],
        [ 0.0556434, -0.2040259,  1.0572252]
    ], dtype=lab.dtype, device=lab.device)

    # Reshape for matrix multiplication
    xyz_flat = xyz.view(3, -1)  # (3, H*W)
    rgb_flat = torch.matmul(matrix_xyz_to_rgb, xyz_flat)  # (3, H*W)

    # Reshape back to (3, H, W)
    rgb = rgb_flat.view(3, lab.shape[1], lab.shape[2])

    # Correzione gamma
    mask = rgb > 0.0031308
    rgb[mask] = 1.055 * torch.pow(rgb[mask], 1.0 / 2.4) - 0.055
    rgb[~mask] = 12.92 * rgb[~mask]

    rgb = torch.clamp(rgb, 0, 1)

    if normalize:
        rgb = torch.mul(rgb, 255.0)

    return rgb

# Live Portrait
#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/crop.py
def parse_pt2_from_pt101(pt101, use_lip=True):
    """
    parsing the 2 points according to the 101 points, which cancels the roll
    """
    # the former version use the eye center, but it is not robust, now use interpolation
    pt_left_eye = np.mean(pt101[[39, 42, 45, 48]], axis=0)  # left eye center
    pt_right_eye = np.mean(pt101[[51, 54, 57, 60]], axis=0)  # right eye center

    if use_lip:
        # use lip
        pt_center_eye = (pt_left_eye + pt_right_eye) / 2
        pt_center_lip = (pt101[75] + pt101[81]) / 2
        pt2 = np.stack([pt_center_eye, pt_center_lip], axis=0)
    else:
        pt2 = np.stack([pt_left_eye, pt_right_eye], axis=0)

    return pt2

def parse_pt2_from_pt98(pt98, use_lip=True, use_mean_eyes=False):
    """
    parsing the 2 points according to the 98 points, which cancels the roll
    """
    if use_mean_eyes:
        pt_left_eye = np.mean(pt98[[66, 60, 62, 64]], axis=0)  # Average of left eye points
        pt_right_eye = np.mean(pt98[[74, 68, 70, 72]], axis=0)  # Average of right eye points
    else:
        pt_left_eye = pt98[96] # Specific left eye point
        pt_right_eye = pt98[97] # Specific right eye point

    if use_lip:
        # use lip
        pt_center_eye = (pt_left_eye + pt_right_eye) / 2
        pt_center_lip = (pt98[76] + pt98[82]) / 2
        pt2 = np.stack([pt_center_eye, pt_center_lip], axis=0)
    else:
        pt2 = np.stack([pt_left_eye, pt_right_eye], axis=0)

    return pt2

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/crop.py
def parse_pt2_from_pt106(pt106, use_lip=True, use_mean_eyes=False):
    """
    parsing the 2 points according to the 106 points, which cancels the roll
    """
    if use_mean_eyes:
        pt_left_eye = np.mean(pt106[[33, 35, 40, 39]], axis=0)  # Average of left eye points
        pt_right_eye = np.mean(pt106[[87, 89, 94, 93]], axis=0)  # Average of right eye points
    else:
        pt_left_eye = pt106[38] # Specific left eye point
        pt_right_eye = pt106[88] # Specific right eye point

    if use_lip:
        # use lip
        pt_center_eye = (pt_left_eye + pt_right_eye) / 2
        pt_center_lip = (pt106[52] + pt106[61]) / 2
        pt2 = np.stack([pt_center_eye, pt_center_lip], axis=0)
    else:
        pt2 = np.stack([pt_left_eye, pt_right_eye], axis=0)

    return pt2

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/crop.py
def parse_pt2_from_pt203(pt203, use_lip=True, use_mean_eyes=False):
    """
    parsing the 2 points according to the 203 points, which cancels the roll
    """
    if use_mean_eyes:
        pt_left_eye = np.mean(pt203[[0, 6, 12, 18]], axis=0)  # Average of left eye points
        pt_right_eye = np.mean(pt203[[24, 30, 36, 42]], axis=0)  # Average of right eye points
    else:
        pt_left_eye = pt203[197]  # Specific left eye point
        pt_right_eye = pt203[198]  # Specific right eye point

    if use_lip:
        # use lip
        pt_center_eye = (pt_left_eye + pt_right_eye) / 2
        pt_center_lip = (pt203[48] + pt203[66]) / 2
        pt2 = np.stack([pt_center_eye, pt_center_lip], axis=0)
    else:
        pt2 = np.stack([pt_left_eye, pt_right_eye], axis=0)

    return pt2

def parse_pt2_from_pt478(pt478, use_lip=True, use_mean_eyes=False):
    """
    parsing the 2 points according to the 203 points, which cancels the roll
    """
    if use_mean_eyes:
        pt_left_eye = np.mean(pt478[[472, 471, 470, 469]], axis=0)  # Average of left eye points
        pt_right_eye = np.mean(pt478[[477, 476, 475, 474]], axis=0)  # Average of right eye points
    else:
        pt_left_eye = pt478[468]  # Specific left eye point
        pt_right_eye = pt478[473]  # Specific right eye point

    if use_lip:
        # use lip
        pt_center_eye = (pt_left_eye + pt_right_eye) / 2
        pt_center_lip = (pt478[61] + pt478[291]) / 2
        pt2 = np.stack([pt_center_eye, pt_center_lip], axis=0)
    else:
        pt2 = np.stack([pt_left_eye, pt_right_eye], axis=0)

    return pt2

def parse_pt2_from_pt68(pt68, use_lip=True):
    """
    parsing the 2 points according to the 68 points, which cancels the roll
    """
    lm_idx = np.array([31, 37, 40, 43, 46, 49, 55], dtype=np.int32) - 1
    if use_lip:
        pt5 = np.stack([
            np.mean(pt68[lm_idx[[1, 2]], :], 0),  # left eye
            np.mean(pt68[lm_idx[[3, 4]], :], 0),  # right eye
            pt68[lm_idx[0], :],  # nose
            pt68[lm_idx[5], :],  # lip
            pt68[lm_idx[6], :]   # lip
        ], axis=0)

        pt2 = np.stack([
            (pt5[0] + pt5[1]) / 2,
            (pt5[3] + pt5[4]) / 2
        ], axis=0)
    else:
        pt2 = np.stack([
            np.mean(pt68[lm_idx[[1, 2]], :], 0),  # left eye
            np.mean(pt68[lm_idx[[3, 4]], :], 0),  # right eye
        ], axis=0)

    return pt2

def parse_pt2_from_pt5(pt5, use_lip=True):
    """
    parsing the 2 points according to the 5 points, which cancels the roll
    """
    pt_left_eye = pt5[0] # Specific left eye point
    pt_right_eye = pt5[1] # Specific right eye point

    if use_lip:
        # use lip
        pt_center_eye = (pt_left_eye + pt_right_eye) / 2
        pt_center_lip = (pt5[3] + pt5[4]) / 2
        pt2 = np.stack([pt_center_eye, pt_center_lip], axis=0)
    else:
        pt2 = np.stack([pt_left_eye, pt_right_eye], axis=0)

    return pt2

def parse_pt2_from_pt9(pt9, use_lip=True):
    '''
    parsing the 2 points according to the 9 points, which cancels the roll
    ['right eye right', 'right eye left', 'left eye right', 'left eye left', 'nose tip', 'lip right', 'lip left', 'upper lip', 'lower lip']
    '''
    if use_lip:
        pt9 = np.stack([
            (pt9[2] + pt9[3]) / 2, # left eye
            (pt9[0] + pt9[1]) / 2, # right eye
            pt9[4],
            (pt9[5] + pt9[6] ) / 2 # lip
        ], axis=0)
        pt2 = np.stack([
            (pt9[0] + pt9[1]) / 2, # eye
            pt9[3] # lip
        ], axis=0)
    else:
        pt2 = np.stack([
            (pt9[2] + pt9[3]) / 2,
            (pt9[0] + pt9[1]) / 2,
        ], axis=0)

    return pt2

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/crop.py
def parse_pt2_from_pt_x(pts, use_lip=True, use_mean_eyes=False):
    if pts.shape[0] == 101:
        pt2 = parse_pt2_from_pt101(pts, use_lip=use_lip)
    elif pts.shape[0] == 106:
        pt2 = parse_pt2_from_pt106(pts, use_lip=use_lip, use_mean_eyes=use_mean_eyes)
    elif pts.shape[0] == 68:
        pt2 = parse_pt2_from_pt68(pts, use_lip=use_lip)
    elif pts.shape[0] == 5:
        pt2 = parse_pt2_from_pt5(pts, use_lip=use_lip)
    elif pts.shape[0] == 203:
        pt2 = parse_pt2_from_pt203(pts, use_lip=use_lip, use_mean_eyes=use_mean_eyes)
    elif pts.shape[0] == 98:
        pt2 = parse_pt2_from_pt98(pts, use_lip=use_lip, use_mean_eyes=use_mean_eyes)
    elif pts.shape[0] == 478:
        pt2 = parse_pt2_from_pt478(pts, use_lip=use_lip, use_mean_eyes=use_mean_eyes)
    elif pts.shape[0] > 101:
        # take the first 101 points
        pt2 = parse_pt2_from_pt101(pts[:101], use_lip=use_lip)
    elif pts.shape[0] == 9:
        pt2 = parse_pt2_from_pt9(pts, use_lip=use_lip)
    else:
        raise Exception(f'Unknow shape: {pts.shape}')

    if not use_lip:
        # NOTE: to compile with the latter code, need to rotate the pt2 90 degrees clockwise manually
        v = pt2[1] - pt2[0]
        pt2[1, 0] = pt2[0, 0] - v[1]
        pt2[1, 1] = pt2[0, 1] + v[0]

    return pt2

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/crop.py
def parse_rect_from_landmark(
    pts,
    scale=1.5,
    need_square=True,
    vx_ratio=0,
    vy_ratio=0,
    use_deg_flag=False,
    **kwargs
):
    """parsing center, size, angle from 101/68/5/x landmarks
    vx_ratio: the offset ratio along the pupil axis x-axis, multiplied by size
    vy_ratio: the offset ratio along the pupil axis y-axis, multiplied by size, which is used to contain more forehead area

    judge with pts.shape
    """
    pt2 = parse_pt2_from_pt_x(pts, use_lip=kwargs.get('use_lip', True), use_mean_eyes=kwargs.get('use_mean_eyes', False))

    uy = pt2[1] - pt2[0]
    l = np.linalg.norm(uy)
    if l <= 1e-3:
        uy = np.array([0, 1], dtype=np.float32)
    else:
        uy /= l
    ux = np.array((uy[1], -uy[0]), dtype=np.float32)

    # the rotation degree of the x-axis, the clockwise is positive, the counterclockwise is negative (image coordinate system)
    # print(uy)
    # print(ux)
    angle = acos(ux[0])
    if ux[1] < 0:
        angle = -angle

    # rotation matrix
    M = np.array([ux, uy])

    # calculate the size which contains the angle degree of the bbox, and the center
    center0 = np.mean(pts, axis=0)
    rpts = (pts - center0) @ M.T  # (M @ P.T).T = P @ M.T
    lt_pt = np.min(rpts, axis=0)
    rb_pt = np.max(rpts, axis=0)
    center1 = (lt_pt + rb_pt) / 2

    size = rb_pt - lt_pt
    if need_square:
        m = max(size[0], size[1])
        size[0] = m
        size[1] = m

    size *= scale  # scale size
    center = center0 + ux * center1[0] + uy * center1[1]  # counterclockwise rotation, equivalent to M.T @ center1.T
    center = center + ux * (vx_ratio * size) + uy * \
        (vy_ratio * size)  # considering the offset in vx and vy direction

    if use_deg_flag:
        angle = degrees(angle)

    return center, size, angle

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/crop.py
def _estimate_similar_transform_from_pts(
    pts,
    dsize,
    scale=1.5,
    vx_ratio=0,
    vy_ratio=-0.1,
    flag_do_rot=True,
    **kwargs
):
    """ calculate the affine matrix of the cropped image from sparse points, the original image to the cropped image, the inverse is the cropped image to the original image
    pts: landmark, 101 or 68 points or other points, Nx2
    scale: the larger scale factor, the smaller face ratio
    vx_ratio: x shift
    vy_ratio: y shift, the smaller the y shift, the lower the face region
    rot_flag: if it is true, conduct correction
    """
    center, size, angle = parse_rect_from_landmark(
        pts, scale=scale, vx_ratio=vx_ratio, vy_ratio=vy_ratio,
        use_lip=kwargs.get('use_lip', True),
        use_mean_eyes=kwargs.get('use_mean_eyes', False)
    )

    s = dsize / size[0]  # scale
    tgt_center = np.array([dsize / 2, dsize / 2], dtype=np.float32)  # center of dsize

    if flag_do_rot:
        costheta, sintheta = cos(angle), sin(angle)
        cx, cy = center[0], center[1]  # ori center
        tcx, tcy = tgt_center[0], tgt_center[1]  # target center
        # need to infer
        M_INV = np.array(
            [[s * costheta, s * sintheta, tcx - s * (costheta * cx + sintheta * cy)],
             [-s * sintheta, s * costheta, tcy - s * (-sintheta * cx + costheta * cy)]],
            dtype=np.float32
        )
    else:
        M_INV = np.array(
            [[s, 0, tgt_center[0] - s * center[0]],
             [0, s, tgt_center[1] - s * center[1]]],
            dtype=np.float32
        )

    M_INV_H = np.vstack([M_INV, np.array([0, 0, 1])])
    M = np.linalg.inv(M_INV_H)

    # M_INV is from the original image to the cropped image, M is from the cropped image to the original image
    return M_INV, M[:2, ...]

def warp_face_by_face_landmark_x(img, pts, **kwargs):
    dsize = kwargs.get('dsize', 224)  # 512
    scale = kwargs.get('scale', 1.5)  # 1.5 | 1.6 | 2.5
    vy_ratio = kwargs.get('vy_ratio', -0.1)  # -0.0625 | -0.1 | -0.125
    interpolation = kwargs.get('interpolation', v2.InterpolationMode.BILINEAR)

    # pad image by image size
    img = pad_image_by_size(img, dsize)
    #if pts.shape[0] == 5:
    #    scale *= 2.20
    #    vy_ratio += (-vy_ratio / 2.20)

    M_o2c, M_c2o = _estimate_similar_transform_from_pts(
        pts,
        dsize=dsize,
        scale=scale,
        vy_ratio=vy_ratio,
        flag_do_rot=kwargs.get('flag_do_rot', True),
    )

    t = trans.SimilarityTransform()
    t.params[0:2] = M_o2c
    img = v2.functional.affine(img, t.rotation*57.2958, translate=(t.translation[0], t.translation[1]), scale=t.scale, shear=(0.0, 0.0), interpolation=interpolation, center=(0, 0))
    img = v2.functional.crop(img, 0,0, dsize, dsize)

    return img, M_o2c, M_c2o

def create_faded_inner_mask(size, border_thickness, fade_thickness, blur_radius=3, device='cuda'):
    """
    Create a mask with a thick black border and a faded white center towards the border (optimized version).
    The white edges are smoothed using Gaussian blur.

    Parameters:
    - size: Tuple (height, width) for the mask size.
    - border_thickness: The thickness of the outer black border.
    - fade_thickness: The thickness over which the white center fades into the black border.
    - blur_radius: The radius for the Gaussian blur to smooth the white edges.
    - device: Device to perform the computation ('cuda' for GPU, 'cpu' for CPU).

    Returns:
    - mask: A PyTorch tensor containing the mask.
    """
    height, width = size
    mask = torch.zeros((height, width), dtype=torch.float32, device=device)  # Start with a black mask

    # Define the inner region
    inner_start = border_thickness
    inner_end_x = width - border_thickness
    inner_end_y = height - border_thickness

    # Create grid for distance calculations on the specified device
    y_indices, x_indices = torch.meshgrid(torch.arange(height, device=device),
                                          torch.arange(width, device=device), indexing='ij')

    # Calculate distances to the nearest border for each point
    dist_to_left = x_indices - inner_start
    dist_to_right = inner_end_x - x_indices - 1
    dist_to_top = y_indices - inner_start
    dist_to_bottom = inner_end_y - y_indices - 1

    # Calculate minimum distance to any border
    dist_to_border = torch.minimum(torch.minimum(dist_to_left, dist_to_right),
                                   torch.minimum(dist_to_top, dist_to_bottom))

    # Mask inside the fading region
    fade_region = (dist_to_border >= 0) & (dist_to_border < fade_thickness)
    mask[fade_region] = dist_to_border[fade_region] / fade_thickness

    # Mask in the full white region
    white_region = dist_to_border >= fade_thickness
    mask[white_region] = 1.0

    # Apply Gaussian blur to smooth the white edges
    mask = mask.unsqueeze(0).unsqueeze(0)  # Add batch and channel dimensions for Gaussian blur
    mask = torchvision.transforms.functional.gaussian_blur(mask, kernel_size=(blur_radius, blur_radius), sigma=(blur_radius / 2))
    mask = mask.squeeze()  # Remove extra dimensions

    return mask

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/crop.py
def prepare_paste_back(mask_crop, crop_M_c2o, dsize, interpolation=v2.InterpolationMode.BILINEAR):
    """prepare mask for later image paste back
    """
    t = trans.SimilarityTransform()
    t.params[0:2] = crop_M_c2o

    # pad image by image size
    mask_crop = pad_image_by_size(mask_crop, (dsize[0], dsize[1]))

    mask_ori = v2.functional.affine(mask_crop, t.rotation*57.2958, translate=(t.translation[0], t.translation[1]), scale=t.scale, shear=(0.0, 0.0), interpolation=interpolation, center=(0, 0))
    mask_ori = v2.functional.crop(mask_ori, 0,0, dsize[0], dsize[1]) # cols, rows
    mask_ori = torch.div(mask_ori.type(torch.float32), 255.)

    return mask_ori

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/crop.py
def paste_back(img_crop, M_c2o, img_ori, mask_ori, interpolation=v2.InterpolationMode.BILINEAR):
    """paste back the image
    """
    dsize = (img_ori.shape[1], img_ori.shape[2])
    t = trans.SimilarityTransform()
    t.params[0:2] = M_c2o

    # pad image by image size
    img_crop = pad_image_by_size(img_crop, (img_ori.shape[1], img_ori.shape[2]))

    output = v2.functional.affine(img_crop, t.rotation*57.2958, translate=(t.translation[0], t.translation[1]), scale=t.scale, shear=(0.0, 0.0), interpolation=interpolation, center=(0, 0))
    output = v2.functional.crop(output, 0,0, dsize[0], dsize[1]) # cols, rows

    # Converti i tensor al tipo appropriato prima delle operazioni in-place
    output = output.float()  # Converte output in torch.float32
    mask_ori = mask_ori.float()  # Assicura che mask_ori sia float per operazioni compatibili
    img_ori = img_ori.float()  # Assicura che img_ori sia float

    # Ottimizzazione con operazioni in-place
    output.mul_(mask_ori)  # In-place multiplication
    output.add_(img_ori.mul_(1 - mask_ori))  # In-place addition and multiplication
    output.clamp_(0, 255)  # In-place clamping
    output = output.to(torch.uint8)

    return output

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/live_portrait_wrapper.py
def calculate_distance_ratio(lmk: np.ndarray, idx1: int, idx2: int, idx3: int, idx4: int, eps: float = 1e-6) -> np.ndarray:
    return (np.linalg.norm(lmk[:, idx1] - lmk[:, idx2], axis=1, keepdims=True) /
            (np.linalg.norm(lmk[:, idx3] - lmk[:, idx4], axis=1, keepdims=True) + eps))

def calc_eye_close_ratio(lmk: np.ndarray, target_eye_ratio: np.ndarray = None) -> np.ndarray:
    lefteye_close_ratio = calculate_distance_ratio(lmk, 6, 18, 0, 12)
    righteye_close_ratio = calculate_distance_ratio(lmk, 30, 42, 24, 36)
    if target_eye_ratio is not None:
        return np.concatenate([lefteye_close_ratio, righteye_close_ratio, target_eye_ratio], axis=1)
    else:
        return np.concatenate([lefteye_close_ratio, righteye_close_ratio], axis=1)

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/live_portrait_wrapper.py
def calc_lip_close_ratio(lmk: np.ndarray) -> np.ndarray:
    return calculate_distance_ratio(lmk, 90, 102, 48, 66)

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/camera.py
def headpose_pred_to_degree(pred):
    """
    pred: (bs, 66) or (bs, 1) or others
    """
    if pred.ndim > 1 and pred.shape[1] == 66:
        # NOTE: note that the average is modified to 97.5
        device = pred.device
        idx_tensor = [idx for idx in range(0, 66)]
        idx_tensor = torch.FloatTensor(idx_tensor).to(device)
        pred = torch.nn.functional.softmax(pred, dim=1)
        degree = torch.sum(pred*idx_tensor, axis=1) * 3 - 97.5

        return degree

    return pred

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/camera.py
def get_rotation_matrix(pitch_, yaw_, roll_):
    """ the input is in degree
    """
    # transform to radian
    pitch = pitch_ / 180 * np.pi
    yaw = yaw_ / 180 * np.pi
    roll = roll_ / 180 * np.pi

    device = pitch.device

    if pitch.ndim == 1:
        pitch = pitch.unsqueeze(1)
    if yaw.ndim == 1:
        yaw = yaw.unsqueeze(1)
    if roll.ndim == 1:
        roll = roll.unsqueeze(1)

    # calculate the euler matrix
    bs = pitch.shape[0]
    ones = torch.ones([bs, 1]).to(device)
    zeros = torch.zeros([bs, 1]).to(device)
    x, y, z = pitch, yaw, roll

    rot_x = torch.cat([
        ones, zeros, zeros,
        zeros, torch.cos(x), -torch.sin(x),
        zeros, torch.sin(x), torch.cos(x)
    ], dim=1).reshape([bs, 3, 3])

    rot_y = torch.cat([
        torch.cos(y), zeros, torch.sin(y),
        zeros, ones, zeros,
        -torch.sin(y), zeros, torch.cos(y)
    ], dim=1).reshape([bs, 3, 3])

    rot_z = torch.cat([
        torch.cos(z), -torch.sin(z), zeros,
        torch.sin(z), torch.cos(z), zeros,
        zeros, zeros, ones
    ], dim=1).reshape([bs, 3, 3])

    rot = rot_z @ rot_y @ rot_x

    return rot.permute(0, 2, 1)  # transpose

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/live_portrait_wrapper.py
def transform_keypoint(kp_info: dict):
    """
    transform the implicit keypoints with the pose, shift, and expression deformation
    kp: BxNx3
    """
    kp = kp_info['kp']    # (bs, k, 3)
    pitch, yaw, roll = kp_info['pitch'], kp_info['yaw'], kp_info['roll']

    t, exp = kp_info['t'], kp_info['exp']
    scale = kp_info['scale']

    pitch = headpose_pred_to_degree(pitch)
    yaw = headpose_pred_to_degree(yaw)
    roll = headpose_pred_to_degree(roll)

    bs = kp.shape[0]
    if kp.ndim == 2:
        num_kp = kp.shape[1] // 3  # Bx(num_kpx3)
    else:
        num_kp = kp.shape[1]  # Bxnum_kpx3

    rot_mat = get_rotation_matrix(pitch, yaw, roll)    # (bs, 3, 3)

    # Eqn.2: s * (R * x_c,s + exp) + t
    kp_transformed = kp.view(bs, num_kp, 3) @ rot_mat + exp.view(bs, num_kp, 3)
    kp_transformed *= scale[..., None]  # (bs, k, 3) * (bs, 1, 1) = (bs, k, 3)
    kp_transformed[:, :, 0:2] += t[:, None, 0:2]  # remove z, only apply tx ty

    return kp_transformed

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/gradio_pipeline.py
@torch.no_grad()
def update_delta_new_eyeball_direction(eyeball_direction_x, eyeball_direction_y, delta_new, **kwargs):
    if eyeball_direction_x > 0:
            delta_new[0, 11, 0] += eyeball_direction_x * 0.0007
            delta_new[0, 15, 0] += eyeball_direction_x * 0.001
    else:
        delta_new[0, 11, 0] += eyeball_direction_x * 0.001
        delta_new[0, 15, 0] += eyeball_direction_x * 0.0007

    delta_new[0, 11, 1] += eyeball_direction_y * -0.001
    delta_new[0, 15, 1] += eyeball_direction_y * -0.001
    blink = -eyeball_direction_y / 2.

    delta_new[0, 11, 1] += blink * -0.001
    delta_new[0, 13, 1] += blink * 0.0003
    delta_new[0, 15, 1] += blink * -0.001
    delta_new[0, 16, 1] += blink * 0.0003

    return delta_new

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/gradio_pipeline.py
@torch.no_grad()
def update_delta_new_smile(smile, delta_new, **kwargs):
    delta_new[0, 20, 1] += smile * -0.01
    delta_new[0, 14, 1] += smile * -0.02
    delta_new[0, 17, 1] += smile * 0.0065
    delta_new[0, 17, 2] += smile * 0.003
    delta_new[0, 13, 1] += smile * -0.00275
    delta_new[0, 16, 1] += smile * -0.00275
    delta_new[0, 3, 1] += smile * -0.0035
    delta_new[0, 7, 1] += smile * -0.0035

    return delta_new

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/gradio_pipeline.py
@torch.no_grad()
def update_delta_new_wink(wink, delta_new, **kwargs):
    delta_new[0, 11, 1] += wink * 0.001
    delta_new[0, 13, 1] += wink * -0.0003
    delta_new[0, 17, 0] += wink * 0.0003
    delta_new[0, 17, 1] += wink * 0.0003
    delta_new[0, 3, 1] += wink * -0.0003

    return delta_new

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/gradio_pipeline.py
@torch.no_grad()
def update_delta_new_eyebrow(eyebrow, delta_new, **kwargs):
    if eyebrow > 0:
        delta_new[0, 1, 1] += eyebrow * 0.001
        delta_new[0, 2, 1] += eyebrow * -0.001
    else:
        delta_new[0, 1, 0] += eyebrow * -0.001
        delta_new[0, 2, 0] += eyebrow * 0.001
        delta_new[0, 1, 1] += eyebrow * 0.0003
        delta_new[0, 2, 1] += eyebrow * -0.0003

    return delta_new

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/gradio_pipeline.py
@torch.no_grad()
def update_delta_new_lip_variation_zero(lip_variation_zero, delta_new, **kwargs):
    delta_new[0, 19, 0] += lip_variation_zero

    return delta_new

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/gradio_pipeline.py
@torch.no_grad()
def update_delta_new_lip_variation_one(lip_variation_one, delta_new, **kwargs):
    delta_new[0, 14, 1] += lip_variation_one * 0.001
    delta_new[0, 3, 1] += lip_variation_one * -0.0005
    delta_new[0, 7, 1] += lip_variation_one * -0.0005
    delta_new[0, 17, 2] += lip_variation_one * -0.0005

    return delta_new

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/gradio_pipeline.py
@torch.no_grad()
def update_delta_new_lip_variation_two(lip_variation_two, delta_new, **kwargs):
    delta_new[0, 20, 2] += lip_variation_two * -0.001
    delta_new[0, 20, 1] += lip_variation_two * -0.001
    delta_new[0, 14, 1] += lip_variation_two * -0.001

    return delta_new

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/gradio_pipeline.py
@torch.no_grad()
def update_delta_new_lip_variation_three(lip_variation_three, delta_new, **kwargs):
    delta_new[0, 19, 1] += lip_variation_three * 0.001
    delta_new[0, 19, 2] += lip_variation_three * 0.0001
    delta_new[0, 17, 1] += lip_variation_three * -0.0001

    return delta_new

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/gradio_pipeline.py
@torch.no_grad()
def update_delta_new_mov_x(mov_x, delta_new, **kwargs):
    delta_new[0, 5, 0] += mov_x

    return delta_new

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/gradio_pipeline.py
@torch.no_grad()
def update_delta_new_mov_y(mov_y, delta_new, **kwargs):
    delta_new[0, 5, 1] += mov_y

    return delta_new

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/live_portrait_wrapper.py
def calc_combined_eye_ratio(c_d_eyes_i, source_lmk, device='cuda'):
    c_s_eyes = calc_eye_close_ratio(source_lmk[None])
    c_s_eyes_tensor = torch.from_numpy(c_s_eyes).float().to(device)
    c_d_eyes_i_tensor = torch.Tensor([c_d_eyes_i[0][0]]).reshape(1, 1).to(device)
    # [c_s,eyes, c_d,eyes,i]
    combined_eye_ratio_tensor = torch.cat([c_s_eyes_tensor, c_d_eyes_i_tensor], dim=1)

    return combined_eye_ratio_tensor

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/live_portrait_wrapper.py
def calc_combined_lip_ratio(c_d_lip_i, source_lmk, device='cuda'):
    c_s_lip = calc_lip_close_ratio(source_lmk[None])
    c_s_lip_tensor = torch.from_numpy(c_s_lip).float().to(device)
    c_d_lip_i_tensor = torch.Tensor([c_d_lip_i[0]]).to(device).reshape(1, 1) # 1x1
    # [c_s,lip, c_d,lip,i]
    combined_lip_ratio_tensor = torch.cat([c_s_lip_tensor, c_d_lip_i_tensor], dim=1) # 1x2

    return combined_lip_ratio_tensor

#imported from https://github.com/KwaiVGI/LivePortrait/blob/main/src/utils/helper.py
def concat_feat(kp_source: torch.Tensor, kp_driving: torch.Tensor) -> torch.Tensor:
    """
    kp_source: (bs, k, 3)
    kp_driving: (bs, k, 3)
    Return: (bs, 2k*3)
    """
    bs_src = kp_source.shape[0]
    bs_dri = kp_driving.shape[0]
    assert bs_src == bs_dri, 'batch size must be equal'

    feat = torch.cat([kp_source.view(bs_src, -1), kp_driving.view(bs_dri, -1)], dim=1)
    return feat
