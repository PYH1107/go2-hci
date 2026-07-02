from setuptools import find_packages, setup

package_name = 'go2_voice'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/voice.launch.py']),
        ('share/' + package_name + '/audio', [
            'audio/wake.mp3',
            'audio/ok.mp3',
            'audio/unknown.mp3',
            'audio/stop.mp3',
            'audio/timeout.mp3',
            'audio/confirm.mp3',
            'audio/history_museum_intro.mp3',
            'audio/archive_room_intro.mp3',
            'audio/school_of_classified_intro.mp3',
            'audio/hci_lab_intro.mp3',
        ]),
        ('share/' + package_name + '/config', ['config/poses.yaml']),
    ],
    install_requires=['setuptools', 'rclpy', 'faster-whisper', 'edge-tts', 'numpy'],
    zip_safe=True,
    maintainer='may',
    maintainer_email='may@todo.todo',
    description='Go2 voice interaction system',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'voice_cmd = go2_voice.voice_cmd:main',
            'build_prompts = go2_voice.build_prompts:main',
        ],
    },
)
