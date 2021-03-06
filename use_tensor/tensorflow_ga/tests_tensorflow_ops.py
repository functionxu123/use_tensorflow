'''
Created on Sep 5, 2019

@author: cloudin
'''
import tensorflow as tf
import numpy as np

testing_orders=np.array([[2, 2, 3, 2*24*60, 2, 4],
                         [1, 2, 3, 1*24*60, 4, 4],
                         [3, 2, 2, 3*24*60, 3, 5]], dtype=np.int32)

testing_devs=np.array([[0, 2, 2, 0, 1, 3],
                       [3, 2, 3, 0, 1, 2]], dtype=np.int32)
test_dnas=np.array([[17, 4, 5],
                    [2, 6, 8],
                    [3, 9, 27]] , dtype=np.int32)

test_order_dev=np.array([[1, 1],
                         [0, 1],
                         [1, 0]]  ,dtype=np.int32)


def testing_map_fn():
    elems = (np.array([1, 2, 3]), np.array([-1, 1, -1]))
    alternate = tf.map_fn(lambda x: x[0] * x[1], elems, dtype=tf.int64)
    
    test_order_dev_tf=tf.convert_to_tensor(test_order_dev, dtype=tf.int64)
    
    def devind2devid(x):
        tte=tf.where(  tf.equal(test_order_dev_tf[x[0]], 1)  )
        
        return tte[ x[1][x[0]] ][0]
    elems2 = (tf.range(3), np.array([[1,0,0],[1,0,1],[1,0,0]], dtype=np.int32))
    
    #这里注意加上dtype，且要和输入数据对应，否者会有结构不匹配错误
    #而且注意，这里dtype的shape应该和函数返回值形状一致，如：
    #elems = np.array([1, 2, 3])
    #alternates = map_fn(lambda x: (x, -x), elems, dtype=(tf.int64, tf.int64))  #注意这里dtype的shape和返回的shape一致
    #且注意这里返回的值并不是每行一个返回值，而是每行一个返回的对应tensor
    # alternates[0] == [1, 2, 3]
    # alternates[1] == [-1, -2, -3]
    dev=tf.map_fn(devind2devid, elems2, dtype=tf.int64, parallel_iterations=10, back_prop=False)
    
    with tf.Session() as sess:
        a=sess.run([dev, alternate])
        print (a)
        
def testing_scatter_nd():
    ret=np.array([[0,1],[2,1],[2,2]], dtype=np.int32)
    rett=tf.scatter_nd(ret, tf.range(1, 3+1),[4, 4])
    with tf.Session() as sess:
        a=sess.run([rett])
        print (a)


if __name__ == '__main__':
    #testing_map_fn()
    testing_scatter_nd()









